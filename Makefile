clean:
	-find . -type f -name "*.py[co]" -exec rm {} \;
	-find . -type d -name "__pycache__" -exec rm -r {} \;

test: clean
	python setup.py test 

test3: clean
	python3.3 setup.py test

audit:
	pylint --rcfile=pylintrc redisca/
