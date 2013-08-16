[![Build Status](https://travis-ci.org/khamin/redisca.png?branch=master)](https://travis-ci.org/khamin/redisca)

# Installation

Using PyPi (recommended):

	sudo pip install redisca

Using previously downloaded archive:

	wget https://pypi.python.org/packages/source/r/redisca/redisca-X.tar.gz
	tar xvf redisca-X.tar.gz
	sudo python redisca-X/setup.py install

# Key

Key is simple class abstraction over redis keys.
It implements few useful methods:

```python
from redisca import Key

mykey = Key('somekey') # Init key.
mykey.exists() # Check if key exists.
mykey.delete() # Delete key.
```

Default global database connection pointed to localhost:6397/0 but you can override it:

```python
from redis import Redis
conf.db = Redis(...)
```

Custom key database connection setup available as well:

```python
from redisca import Key
from redis import Redis

mykey = Key('somekey', db=Redis())
```

# Hash

Hash extends *Key* and implements dict-style access for key data:

```python
from redisca import conf
from redisca import Hash

from redis import Redis
conf.db = Redis()

myhash = Hash('hashkey')
myhash['foo'] = 'bar'
print(myhash['foo']) # Produces 'bar'

myhash.save() # Save hash.
myhash.delete() # Delete hash.
```

# Model

Model extends *Hash* and brings some powerful features into the game. Let's see how it works:

```python
from redisca import Model
from redisca import Email
from redisca import conf
from redis import Redis
conf.db = Redis()

@conf(prefix='usr')
class User (Model):
	email = Email(
		field='eml', # Define link with 'eml' hash key.
		index=True,  # Enables index support.
		unique=True, # Makes sure that field is unique across db.
	)

	created = DateTime(
		field='created',       # Define link with 'created' hash key.
		new=datetime.utcnow(), # Value which is used as default in User.new()
	)
	
	# Define own class variables without any limitations.

user = User.new() # Init model with random id.
user.email = 'foo@bar.com' # Set email using field

print(user.email)  # Output 'foo@bar.com'
print(user['eml']) # Dict-style is available too

print(user.created)    # Output result of datetime.utcnow()
print(user['created']) # Output integer timestamp of datetime.utcnow()

user.save()   # Saving routines here.
user.delete() # Delete routines here.
```

Load model by id:

```python
user = User('your_id')
```

## Using Indexes.

As shown above User.email index enabled. It helps to find models by field value:

```python
users = User.email.find('foo@bar.com') # List of matched models instances.
```

Subclasses of *RangeIndexField* has a limited support for ranged queries:

```python
users = User.age.range(minval=0, maxval=100, start=50, num=10)
```

Such call is equivalent of:

```sql
SELECT * FROM `users` where `age` BETWEEN 0 AND 100 LIMIT 10 OFFSET 50;
```

## Per-Model Database Configuration

You can setup **inheritable** per-model database connection using *conf* class decorator:

```python
from redisca import Model
from redisca import conf

from redis import Redis

@conf(db=Redis())
class User (Model):
	pass
```

## Key prefix

Model key format is "model_key_prefix:model_id".
Lowercased class name is default prefix but you can use *conf* class decorator to override this behavior as shown in example:

```python
from redisca import Model
from redisca import conf

@conf(prefix='usr')
class User (Model):
	pass
```

Prefix and key are available for reading:

```python
print(User.getprefix()) # Will produce usr

user = User(1)
print(user.getkey()) # Will produce usr:1
```

## Fields

Field is the way how you should control data in your models. Just define class variables with field-specific options and take classic ORM's advantages:

* data validation;
* native python data types support;
* transparent relations between models;
* indexes support (incl. unique indexes).

Available parameters:

* **field** - hash field which is used as value storage.
* **index** - makes field searchable.
* **unique** - tells that value should be unique across database. Model.save() will raise an Exception if model of same class already exists with given value.
* **new** - field value which is used as default in Model.new()

Built-in fields:

* **String** - extends *IndexField* with additional parameters *minlen* and *maxlen*.
* **Email** - extends *IndexField* field with email validation support.
* **Integer** - extends *RangeIndexField* with parameters *minval* and *maxval*. Accepts int and numeric strings. Returns int.
* **Reference** - extends *IndexField* with *cls* (reference class) parameter. Accepts and returns instance of *cls*.
* **MD5Pass** - extends *String* field. Acts like string but converts given string to md5 sum.
* **DateTime** - extends *RangeIndexField* without additional parameters. Accepts datetime and int(timestamp) values. Returns datetime.

## Registry

Each initialized model is saved in registry and returned on each attempt of re-init. Example below always return True:

```python
user1 = User(1)
user2 = User(1)
user1 is user2 # Always is True
```

It is possbile to cleanup registry:

```python
user.free()      # Unregister model instance.
User.free_all()  # Cleanup User's registry.
Model.free_all() # Cleanup registry completely.
```

# Performance

## Lazy Hash Loading

*Redisca* uses lazy hash data loading technique. That means hash data is loaded exactly when it needed.

```python
user = User(1)       # Nothing loaded here.
user['age'] = 26     # And here.
print(user['age'])   # Or even here.
print(user['email']) # But loaded here because it needed.
```

## Diff-based Saving

*Redisca* tracks local hash data changes and uses lots of tricks during writing operations. In another words you don't have to keep in mind how to optimize actual dialog with redis-server. Just use writing operations as you need and *redisca* will try to perform the rest in better way.

## Using Pipelines

Due to performance and transactional reasons Redis.pipeline's are used internally when it possible. You still able to control it by passing custom pipes to save() and delete() methods. Group operations availble as well:

```python
User.save_all()  # Save all registered models of class User.
Model.save_all() # Save all registered models.
```

# Pseudo-Unique Id Generator

*Redisca* can help you with pseudo-unique id generation:

```python
from redisca import hexid
from redisca import intid

print(hexid()) # 59d369790
print(hexid()) # 59d3697bc

print(intid()) # 24116751882
print(intid()) # 24116788848
```

# Flask Support

Integration with your flask apps is very simple:

```python
from redisca import FlaskRedisca

app = Flask()

app.config['REDISCA'] = {
	# redis.StrictRedis constructor kwargs dict.
}

FlaskRedisca(app)
```

Pass optional *autosave=True* parameter to FlaskRedisca constructor and *redisca* will save all known models at the end of request. Unchanged and deleted models instances are ignored. If you want to skip locally changed instances use free() method during request life.

# Python 3.x support

Py3k support is still a sort of experiment but I'm looking carefuly into full compability with cutting-edge builds of CPython. There are no known issues with it actually.
