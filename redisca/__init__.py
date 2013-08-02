# -*- coding: utf-8 -

import re

from sys import version_info


PY3K = version_info[0] == 3
EMAIL_REGEXP = re.compile(r"^[a-z0-9]+[_a-z0-9-]*(\.[_a-z0-9-]+)*@[a-z0-9]+[\.a-z0-9-]*(\.[a-z]{2,4})$")


db = None


def setdb (redis):
	global db
	db = redis


class Key (object):
	def __init__ (self, key):
		self._key = key
		self._exists = None

	def exists (self):
		""" Check if model key exists. """

		if self._exists is None:
			self._exists = db.exists(self._key)

		return self._exists

	def delete (self, pipe=None):
		_pipe = self.pipe(pipe)

		if self._exists is False:
			return

		_pipe.delete(self._key)

		if pipe is None:
			_pipe.execute()

	def pipe (self, pipe=None):
		return db.pipeline(transaction=True) if pipe is None else pipe


class Hash (Key):
	def __init__ (self, key):
		super(Hash, self).__init__(key)

		self._diff = dict()
		self._data = None

	def __getitem__ (self, name):
		if name in self._diff:
			return self._diff[name]

		self.load()
		return self._data[name] if name in self._data else None

	def __setitem__ (self, name, value):
		if self.loaded() and name in self._data and self._data[name] == value:
			pass

		else:
			self._diff[name] = value

	def __delitem__ (self, name):
		self._diff[name] = None

	def load (self):
		""" Load data into hash if needed. """

		if self.loaded():
			return

		self._data = dict()

		for k, v in db.hgetall(self._key).items():
			if PY3K:
				k = k.decode(encoding='UTF-8')
				v = v.decode(encoding='UTF-8')

			self._data[k] = v

		self._exists = bool(len(self._data))

	def loaded (self):
		""" Check if model data is loaded. """
		return self._data is not None

	def unload (self):
		""" Unload model data. """
		self._data = None

	def diff (self):
		return self._diff

	def save (self, pipe=None):
		""" Save model (optionally within given parent pipe). """

		if not len(self._diff):
			return

		_pipe = self.pipe(pipe)

		if self._exists is not False: # Remove hash item.
			for k, v in self._diff.items():
				if v is None:
					_pipe.hdel(self._key, k)

		# Cleanup diff from None values.
		self._diff = dict([i for i in self._diff.items() if i[1] is not None])

		if not len(self._diff):
			return

		if self.loaded():
			self._data.update(self._diff)

		_pipe.hmset(self._key, self._diff)
		self._diff = dict()

		if pipe is None:
			_pipe.execute()

	def delete (self, pipe=None):
		""" Delete model (optionally within given parent pipe). """

		super(Hash, self).delete(pipe)

		self._diff = dict()
		self._data = dict()
		self._exists = False

	def revert (self):
		""" Revert local changes. """
		self._diff = dict()


class Field (object):
	def __init__ (self, field, index=False, unique=False):
		self.index = bool(index)
		self.unique = bool(unique)
		self.field = field

	def __get__ (self, model, owner):
		self.owner = owner

		if model is None:
			return self

		return model[self.field]

	def __set__ (self, model, value):
		model[self.field] = value

	def find (self, val):
		assert self.index or self.unique

		key = index_key(self.owner.prefix(), self.field, val)
		return set([self.owner(model_id) for model_id in db.smembers(key)])

	def pre_save (self, model, pipe=None):
		assert isinstance(model, Model)

		if self.index or self.unique:
			key = index_key(model.prefix(), self.field, model[self.field])

			if self.unique:
				model_id = bytes(model._id, 'utf-8') if PY3K else model._id
				ids = db.smembers(key)
				ids.discard(model._id)

				if len(ids):
					raise Exception('Duplicate key error')

			# Get previous index value.
			if model.loaded() and self.field in model._data:
				prev_val = model._data[self.field]

			else:
				prev_val = db.hget(model._key, self.field)

				if PY3K and prev_val is not None:
					prev_val = prev_val.decode('utf-8')

			if prev_val is not None: # Remove previous value index.
				prev_key = index_key(model.prefix(), self.field, prev_val)
				pipe.srem(prev_key, model._id)

			pipe.sadd(key, model._id)

	def pre_delete (self, model, pipe=None):
		assert isinstance(model, Model)

		if self.index:
			key = index_key(model.prefix(), self.field, model[self.field])
			pipe.srem(key, model._id)


def index_key (prefix, name, value):
	return ':'.join((prefix, name, str(value)))


class Email (Field):
	def __set__ (self, model, value):
		if EMAIL_REGEXP.match(value) == None:
			raise Exception('Email validation failed')

		return super(Email, self).__set__(model, value)


class Reference (Field):
	def __init__ (self, cls, **kw):
		super(Reference, self).__init__(**kw)
		assert issubclass(cls, Model)
		self._cls = cls

	def __get__ (self, model, owner):
		self.owner = owner

		if model is None:
			return self

		return self._cls(model[self.field])

	def __set__ (self, model, parent):
		assert parent.__class__ is self._cls
		model[self.field] = parent._id


class Collection (set):
	def save (self):
		pipe = db.pipeline()

		for model in self:
			model.save(pipe)

		pipe.execute()

	def delete (self):
		pipe = db.pipeline()

		for model in self:
			model.delete(pipe=pipe)

		pipe.execute()


class MetaModel (type):
	def __new__ (mcs, name, bases, dct):
		cls = super(MetaModel, mcs).__new__(mcs, name, bases, dct)

		cls._name2field = dict([(n, f) for (n, f) in cls.__dict__.items() \
			if isinstance(f, Field)]) # field name -> field object

		cls._objects = dict() # id -> model objects registry.
		return cls

	def __call__ (cls, model_id, *args, **kw):
		if PY3K and type(model_id) is bytes:
			model_id = model_id.decode('utf-8')

		else:
			model_id = str(model_id)

		if model_id not in cls._objects:
			cls._objects[model_id] = object.__new__(cls, *args, **kw)
			cls._objects[model_id].__init__(model_id)

		return cls._objects[model_id]


def prefix (val):
	""" Model key prefix class decorator. """

	def f (cls):
		Model._cls2prefix[cls] = val
		return cls

	return f


if PY3K:
	exec('class BaseModel (Hash, metaclass=MetaModel): pass')

else:
	exec('class BaseModel (Hash): __metaclass__ = MetaModel')


class Model (BaseModel):
	_cls2prefix = dict()

	def __init__ (self, model_id):
		self._id = model_id
		super(Model, self).__init__(self.key())

	def delete (self, pipe=None):
		_pipe = self.pipe(pipe)

		for field in self._name2field.values():
			field.pre_delete(self, _pipe)

		super(Model, self).delete(_pipe)

		if pipe is None:
			_pipe.execute()

	def save (self, pipe=None):
		_pipe = self.pipe(pipe)
		diff = self.diff()
		fields = [f for f in self._name2field.values() if f.field in diff]

		for field in fields:
			field.pre_save(self, _pipe)

		super(Model, self).save(_pipe)

		if pipe is None:
			_pipe.execute()

	@classmethod
	def prefix (cls):
		return Model._cls2prefix[cls] \
			if cls in Model._cls2prefix \
				else cls.__name__.lower()

	def key (self):
		return ':'.join((self.prefix(), self._id))

	@classmethod
	def forget_all (cls):
		""" Cleanup models registry. """
		cls._objects = dict()
