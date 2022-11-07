.PHONY: clean formatter help lint readme-toc tag test

SHELL := /bin/bash


help:
	@echo "    help"
	@echo "        Print this help message."
	@echo "    clean"
	@echo "        Remove build artifacts."
	@echo "    formatter"
	@echo "        Apply formatting to the entire codebase."
	@echo "    lint"
	@echo "        Lint code and check if formatting should be applied."
	@echo "    readme-toc"
	@echo "        Create the README's Table of Content"
	@echo "    tag"
	@echo "        Create a giot tag and push remote."
	@echo "    test"
	@echo "        Run tests on tests/."


.ONESHELL:
clean:
	rm *.pyc
	find . -name 'README.md.*' -exec rm -f  {} +

formatter:
	black .

lint:
	echo "No formatter operation defined"

readme-toc:
	# https://github.com/ekalinin/github-markdown-toc
	find ! -path '**node_modules/*' -iname README.md \
		-exec gh-md-toc --insert {} \;

.ONESHELL:
tag:
	git tag $$( cat setup.cfg | grep version | awk -F' = ' '{print $$2}' )
	git push --tags

test:
	echo "No test operation defined"
