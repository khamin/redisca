# -*- coding: utf-8 -

import re

from time import time
from random import randint
from hashlib import md5
from sys import version_info
from datetime import datetime
from redis import StrictRedis
from inspect import isfunction
from inspect import ismethod
from inspect import isbuiltin


PY3K = version_info[0] == 3
EMAIL_REGEXP = re.compile(r"^[a-z0-9]+[_a-z0-9-]*(\.[_a-z0-9-]+)*@[a-z0-9]+[\.a-z0-9-]*(\.[a-z]{2,4})$")


def intid ():
	""" Return pseudo-unique decimal id. """
	return int((time() - 1374000000) * 100000) * 100 + randint(0, 99)


def hexid ():
	""" Return pseudo-unique hexadecimal id. """
	return '%x' % intid()


class BExpr (object):
	EQ = '='
	GT = '>'
	LT = '<'
	GE = '>='
	LE = '<='

	def __init__ (self, operator, field, val):
		assert isinstance(field, Field)

		self.models = None
		self.operator = operator
		self.field = field
		self.val = val

		super(BExpr, self).__init__()

	def __len__ (self):
		self.load()
		return len(self.models)

	def __getitem__ (self, key):
		self.load()
		return self.models[key]

	def __setitem__ (self, key, value):
		raise NotImplementedError()

	def __iter__ (self):
		self.load()
		return iter(self.models)

	def __contains__ (self, item):
		self.load()
		return item in self.models

	def loaded (self):
		return self.models is not None

	def unload (self):
		self.models = None

	def load (self):
		""" Load result into expression. """

		if self.loaded():
			return

		if self.operator == self.EQ:
			self.models = self.field.find(self.val)

		elif self.operator == self.GT:
			self.models = self.field.range(minval='(%d' % int(self.val))

		elif self.operator == self.GE:
			self.models = self.field.range(minval=int(self.val))

		elif self.operator == self.LT:
			self.models = self.field.range(maxval='(%d' % int(self.val))

		elif self.operator == self.LE:
			self.models = self.field.range(maxval='%d' % int(self.val))

		else:
			raise Exception('Unsupported operator type given')


class Field (object):
	def __init__ (self, field, index=False, unique=False, new=None):
		self.new = new
		self.index = bool(index)
		self.unique = bool(unique)
		self.field = field

	def __get__ (self, model, owner):
		self.owner = owner

		if model is None:
			return self

		val = model[self.field]
		return None if val is None else self.from_db(val)

	def __set__ (self, model, value):
		model[self.field] = None if value is None else self.to_db(value)

	def __lt__ (self, other):
		return BExpr(operator=BExpr.LT, field=self, val=other)

	def __le__ (self, other):
		return BExpr(operator=BExpr.LE, field=self, val=other)

	def __gt__ (self, other):
		return BExpr(operator=BExpr.GT, field=self, val=other)

	def __ge__ (self, other):
		return BExpr(operator=BExpr.GE, field=self, val=other)

	def __eq__ (self, other):
		return BExpr(operator=BExpr.EQ, field=self, val=other)

	def from_db (self, val):
		return val

	def to_db (self, val):
		return str(val) if PY3K else unicode(val)


class IndexField (Field):
	""" Base class for fields with exact indexing. """

	def idx_key (self, prefix, val):
		val = self.to_db(val)
		val = str(val) if PY3K else unicode(val)
		return ':'.join((prefix, self.field, val))

	def find (self, val, children=False):
		assert self.index or self.unique
		key = self.idx_key(self.owner.getprefix(), val)
		ids = self.owner.getdb().smembers(key)
		models = [self.owner(model_id) for model_id in ids]

		if children:
			for child in self.owner.inheritors():
				key = self.idx_key(child.getprefix(), val)
				ids = child.getdb().smembers(key)
				models += [child(model_id) for model_id in ids]

		return models

	def choice (self, val, count=1):
		""" Return *count* random model(s) from find() result. """

		assert self.index or self.unique
		key = self.idx_key(self.owner.getprefix(), val)
		ids = self.owner.getdb().srandmember(key, count)

		return None if not len(ids) else \
			[self.owner(model_id) for model_id in ids]

	def save_idx (self, model, pipe=None):
		prev_idx_val = self.prev_idx_val(model)

		if prev_idx_val == model[self.field]:
			return # Nothing to do.

		idx_key = self.idx_key(model.getprefix(), model[self.field])

		if self.unique:
			ids = model.getdb().smembers(idx_key)

			if len(ids):
				ids.discard(bytes(model._id, 'utf-8') if PY3K else model._id)

				if len(ids):
					raise Exception('Duplicate key error')

		prev_idx_key = self.idx_key(model.getprefix(), prev_idx_val)
		pipe.srem(prev_idx_key, model._id)
		pipe.sadd(idx_key, model._id)

	def del_idx (self, model, pipe=None):
		prev_idx_val = self.prev_idx_val(model)
		prev_idx_key = self.idx_key(model.getprefix(), prev_idx_val)
		pipe.srem(prev_idx_key, model._id)

	def prev_idx_val (self, model):
		""" Get previously indexed value. """

		if not model.exists():
			return None

		elif model.loaded() and self.field in model._data:
			return model._data[self.field]

		else:
			prev_val = model.getdb().hget(model.getkey(), self.field)

			return prev_val.decode('utf-8') \
				if PY3K and prev_val is not None \
					else prev_val


class RangeIndexField (Field):
	""" Base class for fields with range indexing. """

	def idx_key (self, prefix):
		return ':'.join((prefix, self.field))

	def find (self, val, children=False):
		return self.range(
			minval=val,
			maxval=val,
			children=children,
		)

	def range (self, minval='-inf', maxval='+inf', start=None, num=None, children=False):
		assert self.index or self.unique

		if num is not None and start is None:
			start = 0

		key = self.idx_key(self.owner.getprefix())
		db = self.owner.getdb()

		if type(minval) is not str:
			minval = self.to_db(minval)

		if type(maxval) is not str:
			maxval = self.to_db(maxval)

		ids = db.zrangebyscore(key, minval, maxval, start=start, num=num)
		models = [self.owner(model_id) for model_id in ids]

		if children:
			for child in self.owner.inheritors():
				key = self.idx_key(child.getprefix())
				db = child.getdb()
				ids = db.zrangebyscore(key, minval, maxval, start=start, num=num)
				models += [child(model_id) for model_id in ids]

		return models

	def save_idx (self, model, pipe=None):
		key = self.idx_key(model.getprefix())
		val = model[self.field]

		if self.unique:
			models = self.find(val, val)

			if len(models) > 1 or len(models) == 1 and models[0] is not model:
				raise Exception('Duplicate key error')

		pipe.zadd(key, **{
			model._id: self.to_db(val)
		})

	def del_idx (self, model, pipe=None):
		key = self.idx_key(model.getprefix())
		pipe.zrem(key, model._id)


class Bool (IndexField):
	def to_db (self, val):
		return 1 if (val and val != '0') else 0

	def from_db (self, val):
		return val == '1' or val == 1


class String (IndexField):
	def __init__ (self, minlen=None, maxlen=None, **kw):
		super(String, self).__init__(**kw)

		if minlen is not None and maxlen is not None:
			assert minlen < maxlen

		self.minlen = minlen
		self.maxlen = maxlen

	def __set__ (self, model, value):
		if value is not None:
			value = str(value) if PY3K else unicode(value)

			if self.minlen is not None and len(value) < self.minlen:
				raise Exception('Minimal length check failed')

			if self.maxlen is not None and len(value) > self.maxlen:
				raise Exception('Maximum length check failed')

		model[self.field] = value


class Email (IndexField):
	def __set__ (self, model, value):
		if value is not None:
			value = value.lower()

			if EMAIL_REGEXP.match(value) == None:
				raise Exception('Email validation failed')

		return super(Email, self).__set__(model, value)

	def idx_key (self, prefix, val):
		if val is not None:
			val = val.lower()

		return super(Email, self).idx_key(prefix, val)

	def find (self, val, children=False):
		if val is not None:
			val = val.lower()

		return super(Email, self).find(val, children)

	def choice (self, val, count=1):
		if val is not None:
			val = val.lower()

		return super(Email, self).choice(val, count)


class Integer (RangeIndexField):
	def __init__ (self, minval=None, maxval=None, **kw):
		super(Integer, self).__init__(**kw)

		if minval is not None and maxval is not None:
			assert minval < maxval

		self.minval = minval
		self.maxval = maxval

	def __set__ (self, model, value):
		if value is not None:
			value = int(value)

			if self.minval is not None and value < self.minval:
				raise Exception('Minimal value check failed')

			if self.maxval is not None and value > self.maxval:
				raise Exception('Maximum value check failed')

		model[self.field] = value

	def to_db (self, val):
		return int(val)

	def from_db (self, val):
		return int(val)


class DateTime (RangeIndexField):
	def to_db (self, val):
		return int(val.strftime('%s') if type(val) is datetime else val)

	def from_db (self, val):
		return datetime.fromtimestamp(int(val))


class MD5Pass (String):
	def __set__ (self, model, value):
		super(MD5Pass, self).__set__(model, value)

		if value is not None:
			val = model[self.field]

			if PY3K:
				val = val.encode('utf-8')

			model[self.field] = md5(val).hexdigest()


class Reference (IndexField):
	def __init__ (self, cls, **kw):
		super(Reference, self).__init__(**kw)
		assert issubclass(cls, Model)
		self._cls = cls

	def find (self, val, children=False):
		if isinstance(val, Model):
			val = val._id

		return super(Reference, self).find(val, children=children)

	def choice (self, val):
		if isinstance(val, Model):
			val = val._id

		return super(Reference, self).choice(val)

	def to_db (self, val):
		return val._id if isinstance(val, Model) else val

	def from_db (self, val):
		return self._cls(val)


class MetaModel (type):
	def __new__ (mcs, name, bases, dct):
		cls = super(MetaModel, mcs).__new__(mcs, name, bases, dct)
		cls._objects = dict() # id -> model objects registry.
		cls._fields = dict()

		for name in dir(cls):
			member = getattr(cls, name)

			if isinstance(member, Field):
				cls._fields[name] = member

		return cls

	def __setattr__ (cls, name, val):
		if isinstance(val, Field):
			cls._fields[name] = val

		super(MetaModel, cls).__setattr__(name, val)

	def __call__ (cls, model_id, *args, **kw):
		if model_id is None:
			model_id = ''

		elif PY3K and type(model_id) is bytes:
			model_id = model_id.decode('utf-8')

		else:
			model_id = str(model_id)

		if model_id not in cls._objects:
			cls._objects[model_id] = object.__new__(cls, *args, **kw)
			cls._objects[model_id].__init__(model_id)

		return cls._objects[model_id]


class conf (object):
	""" Configuration storage and model decorator. """

	db = StrictRedis()

	def __init__ (self, prefix=None, db=None):
		self._prefix = prefix
		self._db = db

	def __call__ (self, cls):
		if self._db is not None:
			cls._db = self._db

		if self._prefix is not None:
			Model._cls2prefix[cls] = self._prefix

		return cls


if PY3K:
	exec('class BaseModel (metaclass=MetaModel): pass')

else:
	exec('class BaseModel (object): __metaclass__ = MetaModel')


class Model (BaseModel):
	_cls2prefix = dict()

	def __init__ (self, model_id):
		self._id = model_id
		self._key = ':'.join((self.getprefix(), self._id))

		self._exists = None
		self._diff = dict()
		self._data = None

	def __len__ (self):
		return len(self.raw_export())

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
			if name in self._diff:
				del self._diff[name]

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

	def exists (self):
		""" Check if model key exists. """

		if self._exists is None:
			self._exists = self.getdb().exists(self._key)

		return self._exists

	def revert (self):
		""" Revert local changes. """
		self._diff = dict()

	def getdiff (self):
		return self._diff.copy()

	def getorigin (self):
		self.load()
		return self._data.copy()

	@classmethod
	def getdb (cls):
		try:
			return cls._db
		
		except:
			return conf.db

	@classmethod
	def getfields (cls):
		""" Return name -> field dict of registered fields. """
		return cls._fields.copy()

	def getid (self):
		return self._id

	def getkey (self):
		return self._key

	@classmethod
	def getprefix (cls):
		if cls not in Model._cls2prefix:
			Model._cls2prefix[cls] = cls.__name__.lower()

		return Model._cls2prefix[cls]

	@classmethod
	def getpipe (cls, pipe=None):
		return cls.getdb().pipeline(transaction=True) if pipe is None else pipe

	@classmethod
	def new (cls, model_id=None):
		""" Return new model with given id and field.new values.
		If model id is None hexid() will be used instead.
		Exception raised if model already exists.

		Notice: if model with such id was initialized previously (already in
		registry) this method will overwrite it with field.new values. """

		if model_id is None:
			model_id = hexid()

		model = cls(model_id)

		if model.exists():
			raise Exception('%s(%s) already exists' % (cls.__name__, model_id))

		return model.fill_new()

	def fill_new (self):
		""" Fill model with *new* values. """

		for name, field in self.getfields().items():
			val = field.new
			val = val() if isfunction(val) or ismethod(val) or isbuiltin(val) else val
			setattr(self, name, val)

		return self

	def raw_export (self):
		""" Return a copy of model raw-data dict. """

		data = self.getorigin()
		data.update(self._diff)
		return {k: v for (k, v) in data.items() if v is not None}

	def export (self, keep_none=False):
		""" Export model fields data as dict. """

		data = dict()

		for name in self.getfields():
			val = getattr(self, name)

			if keep_none or val is not None:
				data[name] = val

		return data

	def load (self):
		""" Load data into hash if needed. """

		if self.loaded():
			return

		self._data = dict()

		if self._exists is False:
			return

		for k, v in self.getdb().hgetall(self._key).items():
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

	def delete (self, pipe=None):
		""" Delete model (optionally within given parent pipe). """

		_pipe = self.getpipe(pipe)

		for field in self.getfields().values():
			if field.index or field.unique:
				field.del_idx(self, _pipe)

		if self._exists is not False:
			_pipe.delete(self._key)

			self._diff = dict()
			self._data = dict()
			self._exists = False

		if pipe is None and len(_pipe):
			_pipe.execute()

	def save (self, pipe=None):
		if not len(self._diff):
			return

		fields = [f for f in self.getfields().values() \
			if f.field in self._diff and (f.index or f.unique)]

		_pipe = self.getpipe(pipe)

		for field in fields:
			field.save_idx(self, _pipe)

		delkeys = []
		loaded = self.loaded()

		for key, val in self.getdiff().items():
			if val is None:
				delkeys.append(key)
				del self._diff[key]

				if loaded and key in self._data:
					del self._data[key]

		if self._exists is not False and len(delkeys):
			_pipe.hdel(self._key, *delkeys)

		if len(self._diff):
			_pipe.hmset(self._key, self._diff)

		if pipe is None and len(_pipe):
			_pipe.execute()

		if loaded:
			self._data.update(self._diff)

		self._exists = True
		self._diff = dict()

	@classmethod
	def save_all (cls, pipe=None):
		""" Save all known models. Deleted models ignored by empty diff. """

		if cls is not Model:
			_pipe = cls.getpipe(pipe)

			for model in cls._objects.values():
				model.save(_pipe)

			if pipe is None and len(_pipe):
				_pipe.execute()

		for child in cls.__subclasses__():
			child.save_all()

	def free (self):
		del self.__class__._objects[self._id]

	@classmethod
	def free_all (cls):
		""" Cleanup models registry. """

		cls._objects = dict()

		for child in cls.__subclasses__():
			child.free_all()

	@classmethod
	def inheritors (cls):
		""" Get model inheritors. """

		subclasses = set()
		classes = [cls]

		while classes:
			parent = classes.pop()

			for child in parent.__subclasses__():
				if child not in subclasses:
					subclasses.add(child)
					classes.append(child)

		return subclasses


class FlaskRedisca (object):
	def __init__ (self, app=None, autosave=False):
		self.autosave = autosave

		if app is not None:
			self.init_app(app)

	def init_app (self, app):
		self.app = app

		conf.db = StrictRedis(**self.app.config['REDISCA'])
		self.app.before_request(self.before_request)
		self.app.teardown_request(self.after_request)

	def before_request (self):
		pass

	def after_request (self, exc):
		if exc is None and self.autosave:
			Model.save_all()

		Model.free_all()
