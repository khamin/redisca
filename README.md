# Hashes

# Model

## Introduction.

Model is a simple extension of *Hash* that brings Fields into the game. You can define custom fields with some useful options and interact with hashes in OOP-manner.

	from redisca import Model
	from redisca import Email
	
	class User (Model):
		email = Email(
			field='eml',
			index=True,
			unique=True,
		)
	
	user = User(1)
	user.email = 'foo@bar.com' # Will validate given email
	
	print(user.email)  # Will output 'foo@bar.com'
	print(user['eml']) # Dict-style is available too
	
	user.save() # Saving routines here.
	user.delete() # Delete routines here.

As you can see Email field definition has some interesting options:

* *field='eml'* defines that field linked to 'eml' hash key.
* *index=True* enables index support for that hash key (look at Fields.indexes section for more information).
* *unique=True* makes sure that User.email is unique across database.

## Registry

Each initialized model is saved in registry and returned on each attempt of re-init. Example below always return True:

	user1 = User(1)
	user2 = User(1)
	user1 is user2 # Always is True

## Configuration

### Connection handler

First step of using *redisca* is setting global connection handler up:

	from redisca import setdb
	from redis import Redis
	setdb(Redis())

### Key prefix

Model key format is %ModelKeyPrefix%:%ModelId%. Lower-cased class name will be used as prefix by default, but you can use *prefix* class decorator to override this behavior like this:

	from redisca import Model
	from redisca import prefix

	@prefix('myprefix')
	class MyModel (Model):
		pass
	
	mymodel = MyModel('foo')
	print(mymodel._key) # Will produce myprefix:foo.

# Fields

Field is the way how you should take control on data in your models. Just define class variables with field-specific options and take classic ORM's advantages:

* data validation;
* native python data types support;
* transparent relations between models;
* indexes support (incl. unique indexes).

Note that you still able to define own class variables without any limitations.


## Email field

## Reference field

## Field index

## Unique fields

## Writing custom fields

### Field callbacks

# Collections

# Performance

## Lazy Hash Loading

*Redisca* uses lazy hash data loading technique. That means hash data is loaded exactly when it needed.

	user = User(1)       # Nothing loaded here.
	user['age'] = 26     # And here.
	print(user['age'])   # Or even here.
	print(user['email']) # But loaded here because it needed.

## Diff-based Saving

*Redisca* tracks local hash data changes and uses lots of tricks during writing operations. In another words you don't have to keep in mind how to optimize actual dialog with redis-server. Just use writing operations as you need and *redisca* will try to perform the rest in better way.

## Using Pipelines

Due to performance and transactional reasons Redis.pipeline's are used internally when it possible. You still able to control it by passing custom pipes to save() and delete() methods.

# Python 3.x support

Py3k support is still a sort of experiment but I'm looking carefuly into full compability with cutting-edge builds of CPython. There are no known issues with it actually.
