/** @import { Core } from '@strapi/strapi' */

const path = require('path');
const { isDatabaseClientKind } = require('@strapi/database');

module.exports = ({ env }) => {
  const client = env('DATABASE_CLIENT', 'sqlite');

  if (!isDatabaseClientKind(client)) {
    throw new Error(
      `Unsupported DATABASE_CLIENT: ${client}. Use "postgres", "mysql", or "sqlite".`
    );
  }

  /** @type {Record<Core.Config.Database.ClientKind, Core.Config.Database['connection']>} */
  const connections = {
    mysql: {
      client: 'mysql',
      connection: {
        host: env('DATABASE_HOST', 'localhost'),
        port: env.int('DATABASE_PORT', 3306),
        database: env('DATABASE_NAME', 'strapi'),
        user: env('DATABASE_USERNAME', 'strapi'),
        password: env('DATABASE_PASSWORD', 'strapi'),
        // MatrixOne reports legacy UTF-8 metadata for four-byte Unicode values.
        // The fixture schema is verified to contain no binary columns.
        // Its derived relation-name column has empty db/table metadata.
        // Other unknown or binary fields continue through next().
        typeCast: env.bool('MATRIXONE_ADAPTER', false) ? (field, next) => {
          if (process.env.MO_NATIVE_METADATA_LOG && /name|title|body/.test(field.name)) {
            require('fs').appendFileSync(process.env.MO_NATIVE_METADATA_LOG, JSON.stringify({db:field.db,table:field.table,name:field.name,type:field.type})+'\n',{mode:0o600});
          }
          if (((field.db === env('DATABASE_NAME') && ['title', 'name', 'body'].includes(field.name))
              || (field.db === '' && field.table === '' && field.name === 'name' && field.type === 'VAR_STRING'))
              && ['STRING', 'VAR_STRING', 'BLOB'].includes(field.type)) {
            return field.string('utf8');
          }
          return next();
        } : undefined,

        ssl: env.bool('DATABASE_SSL', false) && {
          key: env('DATABASE_SSL_KEY', undefined),
          cert: env('DATABASE_SSL_CERT', undefined),
          ca: env('DATABASE_SSL_CA', undefined),
          capath: env('DATABASE_SSL_CAPATH', undefined),
          cipher: env('DATABASE_SSL_CIPHER', undefined),
          rejectUnauthorized: env.bool('DATABASE_SSL_REJECT_UNAUTHORIZED', true),
        },
      },
      pool: { min: env.int('DATABASE_POOL_MIN', 2), max: env.int('DATABASE_POOL_MAX', 10) },
    },
    postgres: {
      client: 'postgres',
      connection: {
        connectionString: env('DATABASE_URL'),
        host: env('DATABASE_HOST', 'localhost'),
        port: env.int('DATABASE_PORT', 5432),
        database: env('DATABASE_NAME', 'strapi'),
        user: env('DATABASE_USERNAME', 'strapi'),
        password: env('DATABASE_PASSWORD', 'strapi'),
        ssl: env.bool('DATABASE_SSL', false) && {
          key: env('DATABASE_SSL_KEY', undefined),
          cert: env('DATABASE_SSL_CERT', undefined),
          ca: env('DATABASE_SSL_CA', undefined),
          capath: env('DATABASE_SSL_CAPATH', undefined),
          cipher: env('DATABASE_SSL_CIPHER', undefined),
          rejectUnauthorized: env.bool('DATABASE_SSL_REJECT_UNAUTHORIZED', true),
        },
        schema: env('DATABASE_SCHEMA', 'public'),
      },
      pool: { min: env.int('DATABASE_POOL_MIN', 2), max: env.int('DATABASE_POOL_MAX', 10) },
    },
    sqlite: {
      client: 'sqlite',
      connection: {
        filename: path.join(__dirname, '..', env('DATABASE_FILENAME', '.tmp/data.db')),
      },
      useNullAsDefault: true,
    },
  };

  return {
    connection: {
      ...connections[client],
      acquireConnectionTimeout: env.int('DATABASE_CONNECTION_TIMEOUT', 60000),
    },
  };
};
