# Hash

Hashes are simple:

	from redisca import setdb
	from redisca import Hash
	
	from redis import Redis
	setdb(Redis())
	
	myhash = Hash('hashkey')
	myhash['foo'] = 'bar'
	print(myhash['foo']) # Produces 'bar'
	
	myhash.save() # Save hash.
	myhash.delete() # Delete hash.

# Model

Model is a simple extension of *Hash* that brings some powerful features into the game. Let's see how it works:

	from redisca import Model
	from redisca import Email
	from redisca import prefix
	from redisca import setdb
	
	from redis import Redis
	setdb(Redis())
	
	@prefix('usr')
	class User (Model):
		email = Email(
			field='eml', # define link with 'eml' hash key.
			index=True,  # enables index support.
			unique=True, # makes sure that field is unique across db.
		)
	
		... # Define class variables without any limitations.
	
	user = User(1) # Init model with id '1'
	user.email = 'foo@bar.com' # Set email using field
	
	print(user.email)  # Will output 'foo@bar.com'
	print(user['eml']) # Dict-style is available too
	
	user.save() # Saving routines here.
	User.email.find('foo@bar.com') # Find models by indexed field. Return [user]
	user.delete() # Delete routines here.

## Key prefix

Model key format is %ModelKeyPrefix%:%ModelId%. Lower-cased class name will be used as prefix by default but you can use *prefix* class decorator to override this behavior like this:

	print(user._key) # Will produce usr:1

## Fields

Field is the way how you should take control on data in your models. Just define class variables with field-specific options and take classic ORM's advantages:

* data validation;
* native python data types support;
* transparent relations between models;
* indexes support (incl. unique indexes).

Available parameters:

* field - hash field which is used as value storage.
* index - makes field searchable.
* unique - tells that value should be unique across database. Model.save() will raise an Exception if model of same class already exists with given value.

Built-in fields:

* *String* - extends *Field* with additional parameters *minlen* and *maxlen*.
* *Email* - extends *String* field with email validation support.
* *Integer* - extends *Field* with parameters *minval* and *maxval*. Accepts int and numeric strings. Returns int.
* *Reference* - extends *Field* with *cls* (reference class) parameter. Accepts and returns instance of *cls*.
* *MD5Pass* - extends *String* field. Acts like string but converts given string to md5 sum.
* *DateTime* - extends *Field* without additional parameters. Accepts datetime and int(timestamp) values. Returns datetime.

## Registry

Each initialized model is saved in registry and returned on each attempt of re-init. Example below always return True:

	user1 = User(1)
	user2 = User(1)
	user1 is user2 # Always is True

It is possbile to cleanup registry:

	user.free()      # Unregister model instance.
	User.free_all()  # Cleanup User's registry.
	Model.free_all() # Cleanup registry completely.

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

Due to performance and transactional reasons Redis.pipeline's are used internally when it possible. You still able to control it by passing custom pipes to save() and delete() methods. Group operations availble as well:

	User.save_all() # Save all registered models of class User.
	User.delete_all() # Delete all registered models of class User.
	
	Model.save_all() # Save all registered models.
	Model.delete_all() # Delete all registered models.

# Flask Support

Integration with your flask apps is very simple:

	from redisca import FlaskRedisca
	
	app = Flask()
	
	app.config['REDISCA'] = {
		# redis.StrictRedis constructor kwargs dict.
	}
	
	FlaskRedisca(app)

# Python 3.x support

Py3k support is still a sort of experiment but I'm looking carefuly into full compability with cutting-edge builds of CPython. There are no known issues with it actually.
