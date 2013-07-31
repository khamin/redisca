# -*- coding: utf-8 -

from unittest import TestCase
from redis import Redis
from redisca import *


Model._redis = Redis()


class Language (Model):
	pass


@prefix('u')
class User (Model):
	name = Field(
		field='name',
		index=True
	)

	lang = Reference(
		Language,
		field='lang',
	)


class ModelTestCase (TestCase):
	def setUp (self):
		Model._redis.flushdb()

	def tearDown (self):
		User._objects = dict()
		Language._objects = dict()

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
		self.assertTrue(Model._redis.exists('u:1'))
		self.assertEqual(Model._redis.hgetall('u:1'), {b'name': b'John Smith'})
		self.assertTrue(Model._redis.exists('u:name:John Smith'))
		self.assertEqual(Model._redis.smembers('u:name:John Smith'), set([b'1']))

		user.delete()
		self.assertTrue(user.loaded())
		self.assertEqual(user.diff(), dict())

		self.assertFalse(Model._redis.exists('u:1'))
		self.assertFalse(Model._redis.exists('u:name:John Smith'))

	def test_reference (self):
		user = User(1)
		user['name'] = 'John Smith'

		Language(1)['name'] = 'English'
		user.lang = Language(1)

		self.assertFalse(user.loaded())
		self.assertEqual(user['lang'], '1')
		self.assertEqual(user.lang, Language(1))

		user.save()

		self.assertFalse(user.loaded())
		self.assertEqual(user['lang'], '1')
		self.assertEqual(user.lang, Language(1))
		self.assertTrue(user.loaded())

		self.assertTrue(Model._redis.exists('u:1'))
		self.assertEqual(Model._redis.hget('u:1', 'lang'), b'1')
		self.assertFalse(Model._redis.exists('language:1'))

		Language(1).save()

		self.assertTrue(Model._redis.exists('language:1'))

		user.delete()
		Language(1).delete()

		self.assertFalse(Model._redis.exists('u:1'))
		self.assertFalse(Model._redis.exists('language:1'))
