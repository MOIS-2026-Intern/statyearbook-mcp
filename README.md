# statyearbook-mcp
행정안전통계연보를 챗봇으로도 만나보세요

## DB 적재 방법
1. parse_yearbook.py가 통계연보 json 파일을 읽어서 db형태에 맞게 json을 재구성하여 parsed_yearbook.json을 생성
2. load_to_postgres.py가 parsed_yearbook.json에 따라 db에 적재
3. embedding.py 가 임베딩 실행하고 db에 적재


```bash
> python load/parse_yearbook.py 통계연보.json
> python load/load_to_postgres.py load/parsed_yearbook.json
```
