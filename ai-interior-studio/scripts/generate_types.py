"""Generate TypeScript component types without Node or network dependencies."""
import argparse
import json
from pathlib import Path


def ts_type(schema):
    if '$ref' in schema:
        return schema['$ref'].rsplit('/', 1)[-1]
    if 'const' in schema:
        return json.dumps(schema['const'])
    if 'enum' in schema:
        return ' | '.join(json.dumps(v) for v in schema['enum'])
    for keyword, separator in [('anyOf', ' | '), ('oneOf', ' | '), ('allOf', ' & ')]:
        if keyword in schema:
            return '(' + separator.join(ts_type(item) for item in schema[keyword]) + ')'
    kind = schema.get('type')
    if kind == 'array':
        if 'prefixItems' in schema:
            return '[' + ', '.join(ts_type(item) for item in schema['prefixItems']) + ']'
        return f'Array<{ts_type(schema.get("items", {}))}>'
    if kind == 'object' or 'properties' in schema:
        required = schema.get('required', [])
        fields = [f'{json.dumps(name)}{"" if name in required else "?"}: {ts_type(value)};' for name, value in schema.get('properties', {}).items()]
        extra = schema.get('additionalProperties', False)
        if extra is not False:
            fields.append(f'[key: string]: {ts_type(extra) if isinstance(extra, dict) else "unknown"};')
        return '{ ' + ' '.join(fields) + ' }' if fields else 'Record<string, unknown>'
    return {'string': 'string', 'integer': 'number', 'number': 'number', 'boolean': 'boolean', 'null': 'null'}.get(kind, 'unknown')


def generate(document):
    return '// Generated from OpenAPI; do not edit.\n' + '\n'.join(
        f'export type {name} = {ts_type(schema)};'
        for name, schema in sorted(document['components']['schemas'].items())
    ) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=Path('services/api/openapi.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generate(json.loads(args.input.read_text(encoding='utf-8'))), encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
