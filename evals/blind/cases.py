"""Blind queries in new wording, labelled from the generator's hidden attributes."""

from evals.cases import (
    PROFILES,
    Case,
    Predicate,
    _suits,
    both,
    city,
    family,
    kind,
    remote,
    sector,
    skill,
)
from evals.dataset import SyntheticJob

TOPIC: list[tuple[str, str, Predicate]] = [
    ("server side engineering internship", "software", family("backend")),
    ("caching and splitting services apart", "software", family("backend")),
    ("pages that load fast for shoppers", "software", family("frontend")),
    ("one person building the whole product end to end", "software", family("fullstack")),
    ("apps for phones that work offline", "software", family("mobile")),
    ("deployment automation and on-call incidents", "fulltime", family("devops")),
    ("terraform", "fulltime", skill("Terraform")),
    ("nightly batch jobs and warehouse modelling", "data", family("data_engineering")),
    ("A/B tests and demand prediction", "data", family("data_science")),
    ("weekly business reporting with charts", "data", family("analytics")),
    ("recommendation models served behind an API", "ml", family("ml")),
    ("language models for customer support in Indian languages", "ml", family("nlp")),
    ("finding defects in camera images", "ml", family("vision")),
    ("penetration testing", "software", family("security")),
    ("automated checks on every code change", "software", family("qa")),
    ("battery powered sensor firmware", "electronics", family("embedded")),
    ("ASIC verification", "electronics", family("vlsi")),
    ("robot arms picking parcels", "mechanical", family("robotics")),
    ("stress analysis of brackets in 3D CAD", "mechanical", family("mechanical")),
    ("cooling simulation for battery packs", "mechanical", family("thermal")),
    ("reducing downtime on an assembly line", "mechanical", family("manufacturing")),
    ("connecting solar farms to the grid", "electronics", family("electrical")),
    ("beams, columns and foundations", "civil", family("civil")),
    ("reactor and distillation simulation", "mechanical", family("chemical")),
    ("interviewing users and prototyping screens", "product", family("design")),
    ("writing requirements and choosing what to build", "product", family("product")),
    ("loan risk and pricing models", "data", family("finance")),
    ("auditing contracts on a public ledger", "software", family("blockchain")),
]

CONSTRAINT: list[tuple[str, str, Predicate]] = [
    (
        "AI for hospitals and clinics",
        "ml",
        both(family("ml", "nlp", "vision"), sector("healthcare")),
    ),
    ("helping growers with irrigation", "ml", sector("agriculture")),
    ("electric scooter and bus makers", "mechanical", sector("mobility")),
    ("small satellite companies", "electronics", sector("space")),
    ("console and mobile games studio", "software", sector("gaming")),
    ("cutting factory emissions", "mechanical", sector("climate")),
    ("lending for small businesses", "software", sector("fintech")),
    ("internship in Kolkata", "software", both(city("Kolkata"), kind("internship"))),
    ("jobs in Ahmedabad", "mechanical", city("Ahmedabad")),
    ("Jaipur roles", "data", city("Jaipur")),
    ("remote machine learning work", "ml", both(family("ml", "nlp"), remote)),
    ("full-time site reliability", "fulltime", both(family("devops"), kind("full-time"))),
    ("kafka and spark", "data", skill("Spark", "Kafka")),
    ("ROS internships", "electronics", both(skill("ROS"), kind("internship"))),
    (
        "warehouse robots or vision for shops",
        "mechanical",
        both(sector("retail", "logistics"), family("robotics", "vision")),
    ),
]

PERSONAL: list[tuple[str, str, tuple[str, ...]]] = [
    ("coding internship that suits me", "software", ("backend", "fullstack", "frontend")),
    ("something in web engineering", "software", ("frontend", "fullstack", "backend")),
    ("roles in artificial intelligence", "ml", ("ml", "nlp", "vision")),
    ("research with neural nets", "ml", ("nlp", "vision", "ml")),
    ("roles crunching business numbers", "data", ("analytics", "data_science", "finance")),
    ("data job for a statistics person", "data", ("analytics", "data_science")),
    ("electronics hardware openings", "electronics", ("embedded", "vlsi")),
    ("circuit level engineering", "electronics", ("vlsi", "embedded", "electrical")),
    ("mechanical core roles", "mechanical", ("mechanical", "thermal", "manufacturing")),
    ("civil engineering openings", "civil", ("civil",)),
    ("roles without much coding", "product", ("product", "design")),
    ("infrastructure job after college", "fulltime", ("devops", "backend")),
]


def build_blind_cases(jobs: list[SyntheticJob]) -> list[Case]:
    cases = []
    for slice_name, rows in (("topic", TOPIC), ("constraint", CONSTRAINT)):
        for query, profile, predicate in rows:
            relevant = [j.key for j in jobs if predicate(j)]
            cases.append(Case(query, profile, slice_name, relevant))
    for query, profile, families in PERSONAL:
        relevant = [j.key for j in jobs if _suits(j, PROFILES[profile], families)]
        cases.append(Case(query, profile, "personal", relevant))
    return [c for c in cases if c.relevant]
