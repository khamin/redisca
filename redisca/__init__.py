# -*- coding: utf-8 -

import re

from six import with_metaclass


EMAIL_REGEXP = re.compile(r"^[a-z0-9]+[_a-z0-9-]*(\.[_a-z0-9-]+)*@[a-z0-9]+[\.a-z0-9-]*(\.[a-z]{2,4})$")


class Key (object):
	def __init__ (self, key):
		self._key = key
		self._exists = None

	def exists (self):
		""" Check if model key exists. """

		if self._exists is None:
			self._exists = Model._redis.exists(self._key)

		return self._exists

	def delete (self, pipe=None):
		_pipe = self.pipe(pipe)

		if self._exists is False:
			return

		_pipe.delete(self._key)

		if pipe is None:
			_pipe.execute()

	def pipe (self, pipe=None):
		return Model._redis.pipeline(transaction=True) if pipe is None else pipe


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
		""" Load data into model if needed. """

		if self.loaded():
			return

		self._data = dict()

		for k, v in Model._redis.hgetall(self._key).items():
			self._data[k.decode(encoding='UTF-8')] = v.decode(encoding='UTF-8')

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
	def __init__ (self, field, index=False):
		self._index = bool(index)
		self._field = field

	def __get__ (self, model, owner):
		if model is None:
			return self

		return model[self._field]

	def __set__ (self, model, value):
		model[self._field] = value

	def after_save (self, model, name, pipe=None):
		pass

	def before_save (self, model, name, pipe=None):
		assert isinstance(model, Model)

		if self._index:
			val = str(model[name])
			key = ':'.join((model.prefix(), name, val))
			pipe.sadd(key, model._id)

	def after_delete (self, model, name, pipe=None):
		pass

	def before_delete (self, model, name, pipe=None):
		assert isinstance(model, Model)

		if self._index:
			val = str(model[name])
			key = ':'.join((model.prefix(), name, val))
			pipe.srem(key, model._id)


def index_key (prefix, fieldname, value):
	return 


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
		if model is None:
			return self

		return self._cls(model[self._field])

	def __set__ (self, model, parent):
		assert parent.__class__ is self._cls
		model[self._field] = parent._id


class Collection (set):
	def save (self):
		pipe = Model._Model._redis.pipeline()

		for model in self:
			model.save(pipe)

		pipe.execute()

	def delete (self):
		pipe = Model._redis.pipeline()

		for model in self:
			model.delete(pipe=pipe)

		pipe.execute()


class MetaModel (type):
	def __new__ (meta, name, bases, dct):
		cls = super(MetaModel, meta).__new__(meta, name, bases, dct)

		cls._name2field = dict([(n, f) for (n, f) in cls.__dict__.items() \
			if isinstance(f, Field)]) # field name -> field object

		cls._objects = dict() # id -> model objects registry.
		return cls

	def __call__ (cls, id, *args, **kw):
		id = str(id)

		if id not in cls._objects:
			cls._objects[id] = object.__new__(cls, *args, **kw)
			cls._objects[id].__init__(id)

		return cls._objects[id]


def prefix (val):
	""" Model key prefix class decorator. """

	def f (cls):
		Model._cls2prefix[cls] = val
		return cls

	return f


class Model (with_metaclass(MetaModel, Hash)):
	_cls2prefix = dict()

	def __init__ (self, id):
		self._id = id
		super(Model, self).__init__(self.key())

	def delete (self, pipe=None):
		_pipe = self.pipe(pipe)

		for name, field in self._name2field.items():
			field.before_delete(self, name, _pipe)

		super(Model, self).delete(_pipe)

		for name, field in self._name2field.items():
			field.after_delete(self, name, _pipe)

		if pipe is None:
			_pipe.execute()

	def save (self, pipe=None):
		_pipe = self.pipe(pipe)

		for name, field in self._name2field.items():
			field.before_save(self, name, _pipe)

		super(Model, self).save(_pipe)

		for name, field in self._name2field.items():
			field.after_save(self, name, _pipe)

		if pipe is None:
			_pipe.execute()

	@classmethod
	def prefix (cls):
		return Model._cls2prefix[cls] if cls in Model._cls2prefix else cls.__name__.lower()

	def key (self):
		return ':'.join((self.prefix(), self._id))

	def children (self, cls):
		key = self._children_refkey(cls)
		return set([cls(id) for id in Model._redis.smembers(key)])

	def add_child (self, model, pipe=None):
		_pipe = self.pipe(pipe)
		key = self._children_refkey(model.__class__)
		_pipe.sadd(key, model._id)

		if pipe is None:
			_pipe.execute()

	def remove_child (self, model, pipe=None):
		_pipe = self.pipe(pipe)
		key = self._children_refkey(model.__class__)
		_pipe.srem(key, model._id)

		if pipe is None:
			_pipe.execute()

	def remove_childen (self, cls, pipe=None):
		_pipe = self.pipe(pipe)
		key = self._children_refkey(cls)
		_pipe.delete(key)

		if pipe is None:
			_pipe.execute()

	def is_child (self, model):
		key = self._children_refkey(model.__class__)
		return Model._redis.sismember(key, model._id)

	def _children_refkey (self, cls):
		return ':'.join((self._key, cls.__name__.lower()))