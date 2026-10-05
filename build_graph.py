import sys
import csv
import json
import re
from datetime import datetime
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD


def normalize_date(date_str):
    """Converts data from YYYY-MM-DD or DD.MM.YYYY to xsd:date format (YYYY-MM-DD)"""
    date_str = date_str.strip()
    if "." in date_str:
        return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
    return date_str


def make_uri(ex_namespace, prefix, name):
    """Forms URI from name under specific prefix"""
    clean_name = str(name).strip().replace(" ", "_")
    return ex_namespace[f"{prefix}/{clean_name}"]


def main():
    if len(sys.argv) != 4:
        print("Usage: python build_graph.py flights.csv params.json graph.ttl")
        sys.exit(1)

    flights_csv = sys.argv[1]
    params_json = sys.argv[2]
    graph_ttl = sys.argv[3]

    # Load params
    with open(params_json, "r", encoding="utf-8") as f:
        params = json.load(f)

    budget_threshold = params.get("budget_threshold_eur", 0)
    long_flight_min = params.get("long_flight_min", 0)

    # Initialization of the graph and namespaces
    g = Graph()
    EX = Namespace("http://example.org/mkr/")
    g.bind("ex", EX)

    # Scheme definition (classes, properties, domains, ranges)
    classes = [
        EX.Flight,
        EX.Airline,
        EX.City,
        EX.Country,
        EX.BudgetFlight,
        EX.LongFlight,
    ]
    for cls in classes:
        g.add((cls, RDF.type, RDFS.Class))

    g.add((EX.BudgetFlight, RDFS.subClassOf, EX.Flight))
    g.add((EX.LongFlight, RDFS.subClassOf, EX.Flight))

    properties = [
        (EX.operatedBy, EX.Flight, EX.Airline),
        (EX.departsFrom, EX.Flight, EX.City),
        (EX.arrivesAt, EX.Flight, EX.City),
        (EX.locatedIn, EX.City, EX.Country),
        (EX.departureDate, EX.Flight, XSD.date),
        (EX.durationMin, EX.Flight, XSD.integer),
        (EX.priceEur, EX.Flight, XSD.decimal),
    ]
    for prop, domain, rng in properties:
        g.add((prop, RDF.type, RDF.Property))
        g.add((prop, RDFS.domain, domain))
        g.add((prop, RDFS.range, rng))

    # Data processing and deduplication
    unique_flights = {}
    country_departure_count = {}

    with open(flights_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize a record ID
            f_id = row["flight_id"].strip().upper()

            # Deduplication (one node per race)
            if f_id in unique_flights:
                continue

            from_country = row["from_country"].strip()
            unique_flights[f_id] = {
                "airline": row["airline"].strip(),
                "from_city": row["from_city"].strip().title(),
                "from_country": from_country,
                "to_city": row["to_city"].strip().title(),
                "to_country": row["to_country"].strip(),
                "dep_date": normalize_date(row["dep_date"]),
                "duration_min": int(row["duration_min"]),
                "price": (
                    float(row["price"])
                    if row.get("price") and row["price"].strip()
                    else None
                ),
                "note": row.get("note", "").strip(),
            }
            # Calculation of flights count for every contry
            country_departure_count[from_country] = (
                country_departure_count.get(from_country, 0) + 1
            )

    # Graph construction
    for f_id, data in unique_flights.items():
        flight_node = EX[f"flight/{f_id}"]

        # Entities nodes
        airline_node = make_uri(EX, "airline", data["airline"])
        from_city_node = make_uri(EX, "city", data["from_city"])
        to_city_node = make_uri(EX, "city", data["to_city"])
        from_country_node = make_uri(EX, "country", data["from_country"])
        to_country_node = make_uri(EX, "country", data["to_country"])

        # Flight relationships
        g.add((flight_node, EX.operatedBy, airline_node))
        g.add((flight_node, EX.departsFrom, from_city_node))
        g.add((flight_node, EX.arrivesAt, to_city_node))
        g.add((from_city_node, EX.locatedIn, from_country_node))
        g.add((to_city_node, EX.locatedIn, to_country_node))

        # Properties of flight entities
        g.add(
            (
                flight_node,
                EX.departureDate,
                Literal(data["dep_date"], datatype=XSD.date),
            )
        )
        g.add(
            (
                flight_node,
                EX.durationMin,
                Literal(data["duration_min"], datatype=XSD.integer),
            )
        )
        if data["price"] is not None:
            g.add(
                (flight_node, EX.priceEur, Literal(data["price"], datatype=XSD.decimal))
            )

        # Human readable labels / names (rdfs:label)
        g.add((airline_node, RDFS.label, Literal(data["airline"], lang="en")))
        g.add((from_city_node, RDFS.label, Literal(data["from_city"], lang="en")))
        g.add((to_city_node, RDFS.label, Literal(data["to_city"], lang="en")))
        g.add((from_country_node, RDFS.label, Literal(data["from_country"], lang="en")))
        g.add((to_country_node, RDFS.label, Literal(data["to_country"], lang="en")))

        # Determination of flight type
        is_budget = data["price"] is not None and data["price"] <= budget_threshold
        is_long = data["duration_min"] >= long_flight_min

        if is_budget:
            g.add((flight_node, RDF.type, EX.BudgetFlight))
        if is_long:
            g.add((flight_node, RDF.type, EX.LongFlight))
        if not is_budget and not is_long:
            g.add((flight_node, RDF.type, EX.Flight))

        # If country is a country with often flights
        if country_departure_count[data["from_country"]] >= 2:
            g.add(
                (flight_node, EX.fromBusyCountry, Literal("true", datatype=XSD.boolean))
            )

        # Delays processing via rdf:Statement
        if data["note"]:
            match = re.search(r"delay=(\d+);\s*by\s*(.+)", data["note"])
            if match:
                delay_min = int(match.group(1))
                source = make_uri(
                    EX,
                    "source",
                    match.group(2).strip().replace(" ", "_").split("/")[-1],
                )

                stmt_node = EX[f"stmt/{f_id}-delay"]
                g.add((stmt_node, RDF.type, RDF.Statement))
                g.add((stmt_node, RDF.subject, flight_node))
                g.add((stmt_node, RDF.predicate, EX.hasDelayMinutes))
                g.add((stmt_node, RDF.object, Literal(delay_min, datatype=XSD.integer)))
                g.add((stmt_node, EX.reportedBy, source))

    # Graph seralization to Turtle format
    g.serialize(destination=graph_ttl, format="turtle")
    print(f"The graph is successfuly saved to '{graph_ttl}'")


if __name__ == "__main__":
    main()
