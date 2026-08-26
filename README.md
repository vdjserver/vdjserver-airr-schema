<a href="https://github.com/linkml/linkml-project-copier"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-teal.json" alt="Copier Badge" style="max-width:100%;"/></a>

# vdjserver-airr-schema

LinkML representation of AIRR Standard schema for VDJServer data modeling and database generation.

## Schema Documentation Website

[https://vdjserver.github.io/vdjserver-airr-schema](https://vdjserver.github.io/vdjserver-airr-schema)

## Repository Structure

* [docs/](docs/) - mkdocs-managed documentation
  * [elements/](docs/elements/) - generated schema documentation
* [examples/](examples/) - Examples of using the schema
* [project/](project/) - project files (these files are auto-generated, do not edit)
* [src/](src/) - source files (edit these)
  * [vdjserver_airr_schema](src/vdjserver_airr_schema)
    * [schema/](src/vdjserver_airr_schema/schema) -- LinkML schema
      (edit this)
    * [datamodel/](src/vdjserver_airr_schema/datamodel) -- generated
      Python datamodel
* [tests/](tests/) - Python tests
  * [data/](tests/data) - Example data

## Source Code Configuration

This repository contains submodules. When doing a `git clone`, those submodules are
not automatically populated, and an additional command is required.

There is an environment file to hold secrets like database password and other configuration information.

```
git clone https://github.com/vdjserver/vdjserver-airr-schema.git
cd vdjserver-airr-schema
git submodule update --init --recursive

# setup database connection and path info
cp .env.defaults .env
nano .env
```

## Makefile commands

Running `make` without a target will display the help message with list of commands. LinkML uses
`just` for running various commands

## Developer Tools

There are several pre-defined command-recipes available.
They are written for the command runner [just](https://github.com/casey/just/).
To list all pre-defined commands, run `just` or `just --list`.

## Credits

This project uses the template [linkml-project-copier](https://github.com/linkml/linkml-project-copier).
