# N = 13 mod 6 = 1

import sys
import json
import csv
from datetime import datetime
import requests

ENDPOINT_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "mkr1/1.0", "Accept": "application/sparql-results+json"}
WIKIDATA_CLASS = "Q1248784"
COUNTRY = "Q142"
WIKIDATA_PROPERTY = "P2044"
THRESHOLD = 200


def generate_queries(wikidata_class, country, wikidata_property, threshold):
    """Generate queries for requests Q1, Q2, Q3"""
    q1 = f"""SELECT ?item ?itemLabel ?value ?website WHERE {{
  ?item wdt:P31 wd:{wikidata_class} ;
        wdt:P17 wd:{country} ;
        wdt:{wikidata_property} ?value .
  FILTER(?value > {threshold})
  OPTIONAL {{ ?item wdt:P856 ?website . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
ORDER BY DESC(?value) ?item
LIMIT 20"""

    q2 = f"""SELECT ?region ?regionLabel (COUNT(?item) AS ?cnt) WHERE {{
  ?item wdt:P31 wd:{wikidata_class} ;
        wdt:P17 wd:{country} ;
        wdt:P131 ?region .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
GROUP BY ?region ?regionLabel
HAVING (COUNT(?item) >= 3)
ORDER BY DESC(?cnt) ?region
LIMIT 10"""

    q3 = f"""SELECT ?item ?itemLabel ?region ?regionLabel ?population WHERE {{
  ?item wdt:P31 wd:{wikidata_class} ;
        wdt:P17 wd:{country} ;
        wdt:P131 ?region .
  ?region wdt:P1082 ?population .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
ORDER BY DESC(?population) ?item
LIMIT 10"""

    return q1, q2, q3


def execute_sparql(query):
    """Execute generated query"""
    response = requests.get(ENDPOINT_URL, params={"query": query}, headers=HEADERS)
    response.raise_for_status()
    data = response.json()

    vars_list = data["head"]["vars"]
    rows = []
    for b in data["results"]["bindings"]:
        row = {v: b[v]["value"] if v in b else "" for v in vars_list}
        rows.append(row)
    return vars_list, rows


def save_csv(filename, vars_list, rows):
    """Save request results to CSV file"""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=vars_list)
        writer.writeheader()
        writer.writerows(rows)


def main():
    # Execution of Q1
    q1_str, q2_str, q3_str = generate_queries(
        WIKIDATA_CLASS, COUNTRY, WIKIDATA_PROPERTY, THRESHOLD
    )
    vars1, rows1 = execute_sparql(q1_str)

    adjusted = False
    new_threshold = THRESHOLD
    if len(rows1) < 5:
        adjusted = True
        new_threshold = THRESHOLD / 2
        print(
            f"Number of rows in Q1 ({len(rows1)}) < 5. Reducing the threshold to {new_threshold}"
        )
        q1_str, _, _ = generate_queries(param, new_threshold)
        vars1, rows1 = execute_sparql(q1_str)

    # Saving SPARQL requests to files
    with open("q1.rq", "w", encoding="utf-8") as f:
        f.write(q1_str)
    with open("q2.rq", "w", encoding="utf-8") as f:
        f.write(q2_str)
    with open("q3.rq", "w", encoding="utf-8") as f:
        f.write(q3_str)

    # Saving of Q1 results to CSV file
    save_csv("q1.csv", vars1, rows1)

    # Saving of Q2 and Q3 results to CSV file
    vars2, rows2 = execute_sparql(q2_str)
    save_csv("q2.csv", vars2, rows2)

    vars3, rows3 = execute_sparql(q3_str)
    save_csv("q3.csv", vars3, rows3)

    # Saving meta.json with a request execution date
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("meta.json", "w", encoding="utf-8") as f:
        json.dump({"retrieved_at": now_str}, f, indent=2, ensure_ascii=False)

    # Creation of ANSWERS.md
    ans_q1 = (
        f"Q1: {rows1[0].get('itemLabel', '')} — {rows1[0].get('value', '')}"
        if rows1
        else "Q1: немає даних"
    )
    ans_q2 = (
        f"Q2: {rows2[0].get('regionLabel', '')} — {rows2[0].get('cnt', '')}"
        if rows2
        else "Q2: немає даних"
    )
    ans_q3 = f"Q3: {rows3[0].get('population', '')}" if rows3 else "Q3: немає даних"

    answers_content = f"{ans_q1}\n{ans_q2}\n{ans_q3}\n"
    if adjusted:
        answers_content += f"Примітка: поріг зменшено до {new_threshold}\n"

    with open("ANSWERS.md", "w", encoding="utf-8") as f:
        f.write(answers_content)

    print(
        "Requests are executed succesfuly. Created files 'q1.csv', 'q2.csv', 'q3.csv', 'meta.json', 'ANSWERS.md', 'q1.rq', 'q2.rq', 'q3.rq'"
    )


if __name__ == "__main__":
    main()
