# -*- coding: utf-8 -

from unittest import TestCase
from datetime import datetime
from time import time
from redis import Redis

from redisca import Model
from redisca import Field
from redisca import Email
from redisca import Integer
from redisca import String
from redisca import MD5Pass
from redisca import DateTime
from redisca import Reference
from redisca import prefix
from redisca import setdb


redis = Redis()
setdb(redis)


@prefix('u')
class User (Model):
	email = Email(
		field='eml',
		unique=True,
	)

	password = MD5Pass(
		field='pass',
		minlen=4,
	)

	name = String(
		field='name',
		minlen=4,
		maxlen=10,
		index=True,
	)

	created = DateTime(
		field='created',
	)

	age = Integer(
		field='age',
		minval=0,
		maxval=100,
	)


class Language (Model):
	name = String(
		field='name'
	)


User.lang = Reference(
	Language,
	field='lang',
	index=True,
)


class SubUser (User):
	pass


class ModelTestCase (TestCase):
	def setUp (self):
		redis.flushdb()

	def tearDown (self):
		User.free_all()
		Language.free_all()

	def test_db (self):
		self.assertTrue(User.db() is redis)
		self.assertTrue(Language.db() is redis)

	def test_registry (self):
		self.assertTrue(User(1) is User(1))
		self.assertTrue(User(1) is not User(2))

		self.assertTrue(Language(1) is Language(1))
		self.assertTrue(Language(1) is not Language(2))

		self.assertTrue(Language(1) is not User(1))
		self.assertTrue(User(1) is not Language(2))

		self.assertTrue(User(1)._id in User._objects)
		self.assertTrue(User(2)._id in User._objects)
		self.assertTrue(Language(1)._id in Language._objects)
		self.assertTrue(Language(2)._id in Language._objects)

		self.assertFalse(User(1)._id in SubUser._objects)
		self.assertFalse(User(2)._id in SubUser._objects)

	def test_attrs (self):
		user1 = User(1)
		user2 = User(2)

		self.assertFalse(user1.loaded())
		self.assertFalse(user2.loaded())
		self.assertEqual(user1.diff(), dict())
		self.assertEqual(user2.diff(), dict())
		self.assertTrue(user1.diff() is not user2.diff())

		self.assertEqual(user1['name'], None)
		self.assertTrue(user1.loaded())
		self.assertFalse(user2.loaded())
		self.assertEqual(user1.diff(), dict())
		self.assertEqual(user2.diff(), dict())

		self.assertEqual(user2['name'], None)
		self.assertTrue(user1.loaded())
		self.assertTrue(user2.loaded())
		self.assertEqual(user1.diff(), dict())
		self.assertEqual(user2.diff(), dict())

		user1['name'] = 'John Smith'

		self.assertEqual(user1['name'], 'John Smith')
		self.assertEqual(user2['name'], None)
		self.assertEqual(user1.diff(), {'name': 'John Smith'})
		self.assertEqual(user2.diff(), dict())

		user2['name'] = 'Sarah Smith'

		self.assertEqual(user1['name'], 'John Smith')
		self.assertEqual(user2['name'], 'Sarah Smith')
		self.assertEqual(user1.diff(), {'name': 'John Smith'})
		self.assertEqual(user2.diff(), {'name': 'Sarah Smith'})

		user1.unload()
		self.assertFalse(user1.loaded())
		self.assertEqual(user1.diff(), {'name': 'John Smith'})
		self.assertEqual(user1['name'], 'John Smith')
		self.assertFalse(user1.loaded())

		user2.revert()
		self.assertTrue(user2.loaded())
		self.assertEqual(user2['name'], None)
		self.assertTrue(user2.loaded())

	def test_save_delete (self):
		user = User(1)
		user.name = 'John Smith'

		user.save()
		self.assertFalse(user.loaded())
		self.assertEqual(user.diff(), dict())
		self.assertTrue(redis.exists('u:1'))
		self.assertEqual(redis.hgetall('u:1'), {b'name': b'John Smith'})
		self.assertTrue(redis.exists('u:name:John Smith'))
		self.assertEqual(redis.smembers('u:name:John Smith'), set([b'1']))

		user.name = 'Steve Gobs'
		user.save()

		self.assertFalse(redis.exists('u:name:John Smith'))
		self.assertEqual(redis.smembers('u:name:Steve Gobs'), set([b'1']))

		user.delete()
		self.assertTrue(user.loaded())
		self.assertEqual(user.diff(), dict())

		self.assertFalse(redis.exists('u:1'))
		self.assertFalse(redis.exists('u:name:John Smith'))

	def test_reference (self):
		self.assertEqual(User.name.choice('John Smith'), None)

		user = User(1)
		user.name = 'John Smith'

		Language(1)['name'] = 'English'
		user.lang = Language(1)

		self.assertFalse(user.loaded())
		self.assertEqual(user['lang'], '1')
		self.assertEqual(user.lang, Language(1))

		user.save()

		# Check references
		self.assertEqual(User.name.find('John Smith'), [User(1)])
		self.assertEqual(User.name.choice('John Smith'), [User(1)])

		self.assertFalse(user.loaded())
		self.assertEqual(user['lang'], '1')
		self.assertEqual(user.lang, Language(1))
		self.assertEqual(User.lang.find(Language(1)), [User(1)])
		self.assertTrue(user.loaded())

		self.assertTrue(redis.exists('u:1'))
		self.assertEqual(redis.hget('u:1', 'lang'), b'1')
		self.assertFalse(redis.exists('language:1'))

		Language(1).save()

		self.assertTrue(redis.exists('language:1'))

		user.delete()
		Language(1).delete()

		self.assertFalse(redis.exists('u:1'))
		self.assertFalse(redis.exists('language:1'))

	def test_dupfield (self):
		user = User(1)
		user.email = 'foo@bar.com'
		user.save()

		user = User(2)
		user.email = 'foo@bar.com'

		self.assertRaises(Exception, user.save)
		user = User(1)
		user.email = None

		self.assertTrue(user.email is None)
		self.assertTrue(user['eml'] is None)
		user.save()

		self.assertTrue(user.email is None)
		self.assertTrue(user['eml'] is None)

		self.assertFalse(redis.scard('u:eml:foo@bar.com'), 0)
		self.assertTrue(redis.exists('u:eml:None'))
		user.save()

	def test_email (self):
		user = User(1)
		user.email = 'foo@bar.com'
		self.assertEqual(user['eml'], 'foo@bar.com')

		with self.assertRaises(Exception):
			user.email = 'foo@@bar.com'

		self.assertEqual(user.email, 'foo@bar.com')

	def test_int (self):
		user = User(1)
		user.age = '26'
		self.assertEqual(user['age'], 26)

		with self.assertRaises(Exception):
			user.age = 'foobar'

		with self.assertRaises(Exception):
			user.age = '-1'

		with self.assertRaises(Exception):
			user.age = -1

		with self.assertRaises(Exception):
			user.age = '101'

		with self.assertRaises(Exception):
			user.age = 101

		self.assertEqual(user.age, 26)

	def test_datetime (self):
		ts = int(time())
		dt = datetime.fromtimestamp(ts)

		user = User(1)
		user.created = dt
		self.assertEqual(user.created, dt)
		self.assertEqual(user['created'], ts)

		user.created = ts
		self.assertEqual(user.created, dt)
		self.assertEqual(user['created'], ts)

		with self.assertRaises(Exception):
			user.created = 'foobar'

	def test_md5pass (self):
		user = User(1)
		user.password = 'foobar'
		self.assertEqual(user.password, '3858f62230ac3c915f300c664312c63f')
		self.assertEqual(user['pass'], '3858f62230ac3c915f300c664312c63f')

		with self.assertRaises(Exception):
			user.password = 'foo'

		with self.assertRaises(Exception):
			user.password = 123

	def test_string (self):
		user = User(1)
		user.name = 'foobar'
		self.assertEqual(user.name, 'foobar')
		self.assertEqual(user['name'], 'foobar')

		user.name = 1234
		self.assertEqual(user.name, '1234')
		self.assertEqual(user['name'], '1234')

		with self.assertRaises(Exception):
			user.name = 'foo'

		with self.assertRaises(Exception):
			user.name = '1234567890_'

	def test_export (self):
		user = User(1)
		user.name = 'foobar'
		self.assertEqual(user.export(), {'name': 'foobar'})

		user.name = None
		self.assertEqual(user.export(), dict())

	def test_get (self):
		user = User(1)
		self.assertEqual(user.get('somekey'), None)

	def test_save_all (self):
		user = User(1)
		user.email = 'foo@bar.com'

		user.lang = Language(1)
		user.lang.name = 'English'

		self.assertFalse(redis.exists('u:1'))
		self.assertFalse(redis.exists('language:1'))

		Model.save_all()

		self.assertTrue(redis.exists('u:1'))
		self.assertTrue(redis.exists('language:1'))
		self.assertTrue(redis.exists('u:lang:1'))
