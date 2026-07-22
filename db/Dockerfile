FROM pgvector/pgvector:pg17

COPY schema.sql /docker-entrypoint-initdb.d/001-statyearbook-schema.sql
COPY profiles /opt/statyearbook/profiles
COPY entrypoint.sh /usr/local/bin/statyearbook-db-entrypoint
RUN chmod 755 /usr/local/bin/statyearbook-db-entrypoint

ENTRYPOINT ["statyearbook-db-entrypoint"]
CMD ["postgres"]
