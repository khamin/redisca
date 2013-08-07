# -*- coding: utf-8 -

import re

from hashlib import md5
from sys import version_info
from datetime import datetime
from redis import StrictRedis


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

		if pipe is None and len(_pipe):
			_pipe.execute()

	@staticmethod
	def pipe (pipe=None):
		return db.pipeline(transaction=True) if pipe is None else pipe


class Hash (Key):
	def __init__ (self, key):
		super(Hash, self).__init__(key)

		self._diff = dict()
		self._data = None

	def __len__ (self):
		return len(self.export())

	def __contains__ (self, name):
		if name in self._diff:
			return True

		self.load()
		return name in self._data

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

	def get (self, name, default=None):
		return self[name] if name in self else default

	def pop (self, name, default=None):
		val = self.get(name, default)
		del self[name]
		return val

	def export (self):
		self.load()
		data = self._data.copy()
		data.update(self._diff)

		return dict([(k, v) for (k, v) in data.items() if v is not None])

	def load (self):
		""" Load data into hash if needed. """

		if self.loaded():
			return

		self._data = dict()

		if self._exists is False:
			return

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
		self._exists = True
		self._diff = dict()

		if pipe is None and len(_pipe):
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
		return self if model is None else model[self.field]

	def __set__ (self, model, value):
		model[self.field] = value

	def find (self, val):
		assert self.index or self.unique
		key = index_key(self.owner.prefix(), self.field, val)
		return [self.owner(model_id) for model_id in db.smembers(key)]

	def choice (self, val, count=1):
		""" Return *count* random model(s) from find() result. """

		assert self.index or self.unique
		key = index_key(self.owner.prefix(), self.field, val)
		ids = db.srandmember(key, count)

		return None if not len(ids) else \
			[self.owner(model_id) for model_id in ids]

	def save_index (self, model, pipe=None):
		key = index_key(model.prefix(), self.field, model[self.field])

		if self.unique:
			model_id = bytes(model._id, 'utf-8') if PY3K else model._id
			ids = db.smembers(key)
			ids.discard(model_id)

			if len(ids):
				raise Exception('Duplicate key error')

		prev_idx_key = self._prev_idx_key(model)

		if prev_idx_key != key:
			pipe.srem(prev_idx_key, model._id)
			pipe.sadd(key, model._id)

	def del_index (self, model, pipe=None):
		# Get previous index value.
		pipe.srem(self._prev_idx_key(model), model._id)

	def _prev_idx_key (self, model):
		""" Get previous value index key. """

		if model.loaded() and self.field in model._data:
			prev_val = model._data[self.field]

		else:
			prev_val = db.hget(model._key, self.field)

			if PY3K and prev_val is not None:
				prev_val = prev_val.decode('utf-8')

		return index_key(model.prefix(), self.field, prev_val)


def index_key (prefix, name, value):
	return ':'.join((prefix, name, str(value)))


class String (Field):
	def __init__ (self, minlen=None, maxlen=None, **kw):
		super(String, self).__init__(**kw)

		if minlen is not None and maxlen is not None:
			assert minlen < maxlen

		self.minlen = minlen
		self.maxlen = maxlen

	def __get__ (self, model, owner):
		val = super(String, self).__get__(model, owner)
		return val.decode('utf-8') if PY3K and type(val) is bytes else val

	def __set__ (self, model, value):
		if value is not None:
			value = str(value)

			if self.minlen is not None and len(value) < self.minlen:
				raise Exception('Minimal length check failed')

			if self.maxlen is not None and len(value) > self.maxlen:
				raise Exception('Maximum length check failed')

		model[self.field] = value


class Email (Field):
	def __set__ (self, model, value):
		if value is not None and EMAIL_REGEXP.match(value) == None:
			raise Exception('Email validation failed')

		return super(Email, self).__set__(model, value)


class Integer (Field):
	def __init__ (self, minval=None, maxval=None, **kw):
		super(Integer, self).__init__(**kw)

		if minval is not None and maxval is not None:
			assert minval < maxval

		self.minval = minval
		self.maxval = maxval

	def __get__ (self, model, owner):
		self.owner = owner
		return self if model is None else int(model[self.field])

	def __set__ (self, model, value):
		if value is not None:
			value = int(value)

			if self.minval is not None and value < self.minval:
				raise Exception('Minimal value check failed')

			if self.maxval is not None and value > self.maxval:
				raise Exception('Maximum value check failed')

		model[self.field] = value


class DateTime (Field):
	def __get__ (self, model, owner):
		self.owner = owner

		if model is None:
			return self

		return None if model[self.field] is None \
			else datetime.fromtimestamp(int(model[self.field]))

	def __set__ (self, model, value):
		if value is not None:
			if type(value) is datetime:
				value = value.strftime('%s')

			value = int(value)

		model[self.field] = value


class MD5Pass (String):
	def __set__ (self, model, value):
		super(MD5Pass, self).__set__(model, value)

		if value is not None:
			val = model[self.field]

			if PY3K:
				val = val.encode('utf-8')

			model[self.field] = md5(val).hexdigest()


class Reference (Field):
	def __init__ (self, cls, **kw):
		super(Reference, self).__init__(**kw)
		assert issubclass(cls, Model)
		self._cls = cls

	def __get__ (self, model, owner):
		self.owner = owner

		if model is None:
			return self

		model_id = model[self.field]
		return None if model_id is None else self._cls(model_id)

	def __set__ (self, model, parent):
		if parent is not None:
			assert parent.__class__ is self._cls
			model[self.field] = parent._id

		else:
			model[self.field] = None

	def find (self, val):
		if isinstance(val, Model):
			val = val._id

		return super(Reference, self).find(val)

	def choice (self, val):
		if isinstance(val, Model):
			val = val._id

		return super(Reference, self).choice(val)


class Collection (set):
	def save (self):
		pipe = db.pipeline()

		for model in self:
			model.save(pipe)

		if len(pipe):
			pipe.execute()

	def delete (self):
		pipe = db.pipeline()

		for model in self:
			model.delete(pipe=pipe)

		if len(pipe):
			pipe.execute()


class MetaModel (type):
	def __new__ (mcs, name, bases, dct):
		cls = super(MetaModel, mcs).__new__(mcs, name, bases, dct)
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

	def fields (self):
		""" Return name -> field dict of registered fields. """
		props = self.__class__.__dict__.items()
		return dict([(k, v) for (k, v) in props if isinstance(v, Field)])

	def delete (self, pipe=None):
		_pipe = self.pipe(pipe)

		for field in self.fields().values():
			if field.index or field.unique:
				field.del_index(self, _pipe)

		super(Model, self).delete(_pipe)

		if pipe is None and len(_pipe):
			_pipe.execute()

	def save (self, pipe=None):
		_pipe = self.pipe(pipe)
		diff = self.diff()

		fields = [f for f in self.fields().values() \
			if f.field in diff and (f.index or f.unique)]

		for field in fields:
			field.save_index(self, _pipe)

		super(Model, self).save(_pipe)

		if pipe is None and len(_pipe):
			_pipe.execute()

	@classmethod
	def save_all (cls, pipe=None):
		""" Save all known models. Deleted models ignored by empty diff. """

		_pipe = cls.pipe(pipe)

		if cls is not Model:
			for model in cls._objects.values():
				model.save(_pipe)

		for child in cls.__subclasses__():
			child.save_all(_pipe)

		if pipe is None and len(_pipe):
			_pipe.execute()

	@classmethod
	def prefix (cls):
		return Model._cls2prefix[cls] \
			if cls in Model._cls2prefix \
				else cls.__name__.lower()

	def key (self):
		return ':'.join((self.prefix(), self._id))

	def free (self):
		del self.__class__._objects[self._id]

	@classmethod
	def free_all (cls):
		""" Cleanup models registry. """

		cls._objects = dict()

		for child in cls.__subclasses__():
			child.free_all()

	@classmethod
	def db (self):
		return db


class FlaskRedisca (object):
	def __init__ (self, app=None):
		if app is not None:
			self.init_app(app)

	def init_app (self, app):
		self.app = app

		setdb(StrictRedis(**self.app.config['REDISCA']))
		self.app.before_request(self.before_request)
		self.app.teardown_request(self.after_request)

	def before_request (self):
		pass

	def after_request (self, exc):
		Model.save_all()
		Model.free_all()
