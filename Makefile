superclean: clean
	rm *.egg

clean:
	-find . -type f -name "*.py[co]" -exec rm {} \;
	-find . -type d -name "__pycache__" -exec rm -r {} \;
	-rm -rf build/
	-rm -rf dist/

test: clean
	python setup.py test

test-pypy: clean
	pypy setup.py test

test3: clean
	python3.3 setup.py test

audit:
	pylint --rcfile=pylintrc redisca/

public: test test3
	python setup.py sdist upload
