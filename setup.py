#!/usr/bin/env python
# -*- coding: utf-8 -

from setuptools import setup, find_packages
PACKAGES = find_packages()


setup(
	name = 'redisca',
	version = '1.0a1',
	packages = PACKAGES,
	package_dir = {'': '.'},
	test_suite = 'redisca.tests',
	author = 'Vitaliy Khamin',
	author_email = 'vitaliykhamin@gmail.com',
	maintainer = 'Vitaliy Khamin',
	maintainer_email = 'vitaliykhamin@gmail.com',
	description = 'Redis Class Abstraction',
	url = 'http://github.com/khamin/redisca',
	zip_safe = True,

	platforms = (
		'any',
	),

	classifiers = (
		'Operating System :: OS Independent',
		'Development Status :: 3 - Alpha',
		'Programming Language :: Python',
		'Topic :: Database',
	),

	install_requires = [
		'six',
		'redis',
	],
)