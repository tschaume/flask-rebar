"""
    Test Swagger Generation
    ~~~~~~~~~~~~~~~~~~~~~~~

    Tests for converting a handler registry to a Swagger specification.

    :copyright: Copyright 2018 PlanGrid, Inc., see AUTHORS.
    :license: MIT, see LICENSE for details.
"""
import unittest

import marshmallow as m

from flask_rebar import HeaderApiKeyAuthenticator
from flask_rebar.rebar import Rebar
from flask_rebar.swagger_generation import SwaggerV2Generator
from flask_rebar.swagger_generation.swagger_generator import _PathArgument as PathArgument
from flask_rebar.swagger_generation.swagger_generator import _flatten as flatten
from flask_rebar.swagger_generation.swagger_generator import _format_path_for_swagger as format_path_for_swagger
from flask_rebar.testing import validate_swagger


class TestFlatten(unittest.TestCase):
    def setUp(self):
        super(TestFlatten, self).setUp()
        self.maxDiff = None

    def test_flatten(self):
        input_ = {
            'type': 'object',
            'title': 'x',
            'properties': {
                'a': {
                    'type': 'object',
                    'title': 'y',
                    'properties': {
                        'b': {'type': 'integer'}
                    }
                },
                'b': {'type': 'string'}
            }
        }

        expected_schema = {'$ref': '#/definitions/x'}

        expected_definitions = {
            'x': {
                'type': 'object',
                'title': 'x',
                'properties': {
                    'a': {'$ref': '#/definitions/y'},
                    'b': {'type': 'string'}
                }
            },
            'y': {
                'type': 'object',
                'title': 'y',
                'properties': {
                    'b': {'type': 'integer'}
                }
            }
        }

        schema, definitions = flatten(input_)
        self.assertEqual(schema, expected_schema)
        self.assertEqual(definitions, expected_definitions)

    def test_flatten_array(self):
        input_ = {
            'type': 'array',
            'title': 'x',
            'items': {
                'type': 'array',
                'title': 'y',
                'items': {
                    'type': 'object',
                    'title': 'z',
                    'properties': {
                        'a': {'type': 'integer'}
                    }
                }
            }
        }

        expected_schema = {
            'type': 'array',
            'title': 'x',
            'items': {
                'type': 'array',
                'title': 'y',
                'items': {'$ref': '#/definitions/z'}
            }
        }

        expected_definitions = {
            'z': {
                'type': 'object',
                'title': 'z',
                'properties': {
                    'a': {'type': 'integer'}
                }
            }
        }

        schema, definitions = flatten(input_)
        self.assertEqual(schema, expected_schema)
        self.assertEqual(definitions, expected_definitions)


class TestFormatPathForSwagger(unittest.TestCase):
    def test_format_path(self):
        res, args = format_path_for_swagger(
            '/projects/<uuid:project_uid>/foos/<foo_uid>'
        )

        self.assertEqual(
            res,
            '/projects/{project_uid}/foos/{foo_uid}'
        )

        self.assertEqual(
            args,
            (
                PathArgument(name='project_uid', type='uuid'),
                PathArgument(name='foo_uid', type='string')
            )
        )

    def test_no_args(self):
        res, args = format_path_for_swagger('/health')

        self.assertEqual(res, '/health')
        self.assertEqual(args, tuple())


class TestSwaggerV2Generator(unittest.TestCase):
    def setUp(self):
        super(TestSwaggerV2Generator, self).setUp()
        self.maxDiff = None

    def test_generate_swagger(self):
        rebar = Rebar()
        registry = rebar.create_handler_registry()

        authenticator = HeaderApiKeyAuthenticator(header='x-auth')
        default_authenticator = HeaderApiKeyAuthenticator(
            header='x-another',
            name='default'
        )

        class HeaderSchema(m.Schema):
            user_id = m.fields.String(load_from='x-userid', required=True)

        class FooSchema(m.Schema):
            __swagger_title__ = 'Foo'

            uid = m.fields.String()
            name = m.fields.String()

        class ListOfFooSchema(m.Schema):
            data = m.fields.Nested(FooSchema, many=True)

        class FooUpdateSchema(m.Schema):
            __swagger_title = 'FooUpdate'

            name = m.fields.String()

        class FooListSchema(m.Schema):
            name = m.fields.String()
            other = m.fields.String()

        @registry.handles(
            rule='/foos/<uuid_string:foo_uid>',
            method='GET',
            marshal_schema={200: FooSchema()},
            headers_schema=HeaderSchema()
        )
        def get_foo(foo_uid):
            """helpful description"""
            pass

        @registry.handles(
            rule='/foos/<foo_uid>',
            method='PATCH',
            marshal_schema={200: FooSchema()},
            request_body_schema=FooUpdateSchema(),
            authenticator=authenticator
        )
        def update_foo(foo_uid):
            pass

        @registry.handles(
            rule='/foos',
            method='GET',
            marshal_schema={200: ListOfFooSchema()},
            query_string_schema=FooListSchema(),
            authenticator=None  # Override the default!
        )
        def list_foos():
            pass

        registry.set_default_authenticator(default_authenticator)

        host = 'swag.com'
        schemes = ['http']
        consumes = ['application/json']
        produces = ['application/vnd.plangrid+json']
        title = 'Test API'
        version = '2.1.0'

        class Error(m.Schema):
            message = m.fields.String()
            details = m.fields.Dict()

        generator = SwaggerV2Generator(
            host=host,
            schemes=schemes,
            consumes=consumes,
            produces=produces,
            title=title,
            version=version,
            default_response_schema=Error()
        )

        swagger = generator.generate(registry)

        expected_swagger = {
            'swagger': '2.0',
            'host': host,
            'info': {
                'title': title,
                'version': version,
                'description': '',
            },
            'schemes': schemes,
            'consumes': consumes,
            'produces': produces,
            'security': [
                {'default': []}
            ],
            'securityDefinitions': {
                'sharedSecret': {
                    'type': 'apiKey',
                    'in': 'header',
                    'name': 'x-auth'
                },
                'default': {
                    'type': 'apiKey',
                    'in': 'header',
                    'name': 'x-another'
                }
            },
            'paths': {
                '/foos/{foo_uid}': {
                    'parameters': [{
                        'name': 'foo_uid',
                        'in': 'path',
                        'required': True,
                        'type': 'string'
                    }],
                    'get': {
                        'operationId': 'get_foo',
                        'description': 'helpful description',
                        'responses': {
                            '200': {
                                'description': 'Foo',
                                'schema': {'$ref': '#/definitions/Foo'}
                            },
                            'default': {
                                'description': 'Error',
                                'schema': {'$ref': '#/definitions/Error'}
                            }
                        },
                        'parameters': [
                            {
                                'name': 'x-userid',
                                'in': 'header',
                                'required': True,
                                'type': 'string'
                            }
                        ]
                    },
                    'patch': {
                        'operationId': 'update_foo',
                        'responses': {
                            '200': {
                                'description': 'Foo',
                                'schema': {'$ref': '#/definitions/Foo'}
                            },
                            'default': {
                                'description': 'Error',
                                'schema': {'$ref': '#/definitions/Error'}
                            }
                        },
                        'parameters': [
                            {
                                'name': 'FooUpdateSchema',
                                'in': 'body',
                                'required': True,
                                'schema': {'$ref': '#/definitions/FooUpdateSchema'}
                            }
                        ],
                        'security': [{'sharedSecret': []}]
                    }
                },
                '/foos': {
                    'get': {
                        'operationId': 'list_foos',
                        'responses': {
                            '200': {
                                'description': 'ListOfFooSchema',
                                'schema': {'$ref': '#/definitions/ListOfFooSchema'}
                            },
                            'default': {
                                'description': 'Error',
                                'schema': {'$ref': '#/definitions/Error'}
                            }
                        },
                        'parameters': [
                            {
                                'name': 'name',
                                'in': 'query',
                                'required': False,
                                'type': 'string'
                            },
                            {
                                'name': 'other',
                                'in': 'query',
                                'required': False,
                                'type': 'string'
                            },
                        ],
                        'security': []
                    }
                }
            },
            'definitions': {
                'Foo': {
                    'type': 'object',
                    'title': 'Foo',
                    'properties': {
                        'uid': {'type': 'string'},
                        'name': {'type': 'string'}
                    }
                },
                'FooUpdateSchema': {
                    'type': 'object',
                    'title': 'FooUpdateSchema',
                    'properties': {
                        'name': {'type': 'string'}
                    }
                },
                'ListOfFooSchema': {
                    'type': 'object',
                    'title': 'ListOfFooSchema',
                    'properties': {
                        'data': {
                            'type': 'array',
                            'items': {'$ref': '#/definitions/Foo'}
                        }
                    }
                },
                'Error': {
                    'type': 'object',
                    'title': 'Error',
                    'properties': {
                        'message': {'type': 'string'},
                        'details': {'type': 'object'}
                    }
                }
            }
        }

        # Uncomment these lines to just dump the result to the terminal:

        # import json
        # print(json.dumps(swagger, indent=2))
        # print(json.dumps(expected_swagger, indent=2))
        # self.assertTrue(False)

        # This will raise an error if validation fails
        validate_swagger(expected_swagger)

        self.assertEqual(swagger, expected_swagger)

    def test_path_parameter_types_must_be_the_same_for_same_path(self):
        rebar = Rebar()
        registry = rebar.create_handler_registry()

        @registry.handles(
            rule='/foos/<string:foo_uid>',
            method='GET'
        )
        def get_foo(foo_uid):
            pass

        @registry.handles(
            rule='/foos/<int:foo_uid>',
            method='PATCH'
        )
        def update_foo(foo_uid):
            pass

        generator = SwaggerV2Generator()

        with self.assertRaises(ValueError):
            generator.generate(registry)


if __name__ == '__main__':
    unittest.main()
