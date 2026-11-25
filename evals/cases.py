"""Labelled retrieval cases.

Labels come from the generator's hidden attributes (role family, sector, location and so on), not
from any ranker. Three slices:

- topic: the query alone decides relevance.
- constraint: the query names a place, sector, type or skill as well as a topic.
- personal: the query is vague and the student's profile decides which postings count.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.search.matching import JobFacts, Preferences, location_match, skill_overlap
from evals.dataset import SyntheticJob

PROFILES: dict[str, dict[str, Any]] = {
    "software": {
        "skills": ["Python", "JavaScript", "React", "SQL", "REST APIs", "Git", "Docker"],
        "preferences": {
            "roles": ["Backend", "Full Stack"],
            "locations": ["Bengaluru", "Pune"],
            "remote_ok": True,
            "job_types": ["internship"],
        },
    },
    "ml": {
        "skills": ["Python", "Machine Learning", "Deep Learning", "PyTorch", "NLP", "SQL"],
        "preferences": {
            "roles": ["Machine Learning", "Computer Vision"],
            "locations": ["Bengaluru", "Hyderabad"],
            "remote_ok": True,
            "job_types": ["internship"],
        },
    },
    "data": {
        "skills": ["SQL", "Python", "Excel", "Statistics", "Data Visualization", "Pandas"],
        "preferences": {
            "roles": ["Data Analytics", "Data Science"],
            "locations": ["Gurugram", "Delhi", "Noida"],
            "remote_ok": True,
            "job_types": ["internship", "full-time"],
        },
    },
    "electronics": {
        "skills": ["C", "C++", "Embedded Systems", "Verilog", "VLSI", "Python", "PCB Design"],
        "preferences": {
            "roles": ["Embedded", "VLSI"],
            "locations": ["Bengaluru", "Hyderabad", "Noida"],
            "remote_ok": False,
            "job_types": ["internship", "full-time"],
        },
    },
    "mechanical": {
        "skills": ["SolidWorks", "ANSYS", "AutoCAD", "MATLAB", "Thermodynamics", "Manufacturing"],
        "preferences": {
            "roles": ["Mechanical Design", "Manufacturing"],
            "locations": ["Pune", "Chennai"],
            "remote_ok": False,
            "job_types": ["internship", "full-time"],
        },
    },
    "civil": {
        "skills": ["AutoCAD", "STAAD Pro", "GIS", "Excel"],
        "preferences": {
            "roles": ["Civil"],
            "locations": ["Delhi", "Mumbai", "Chandigarh"],
            "remote_ok": False,
            "job_types": ["internship", "full-time"],
        },
    },
    "product": {
        "skills": ["Figma", "User Research", "Communication", "SQL", "Product Management", "Excel"],
        "preferences": {
            "roles": ["Product", "Design"],
            "locations": ["Bengaluru", "Mumbai"],
            "remote_ok": True,
            "job_types": ["internship"],
        },
    },
    "fulltime": {
        "skills": ["Java", "Python", "SQL", "Linux", "Docker", "Kubernetes", "AWS"],
        "preferences": {
            "roles": ["Backend", "DevOps and Cloud"],
            "locations": ["Hyderabad", "Pune", "Gurugram"],
            "remote_ok": True,
            "job_types": ["full-time"],
        },
    },
}

Predicate = Callable[[SyntheticJob], bool]


@dataclass
class Case:
    query: str
    profile: str
    slice: str
    relevant: list[str] = field(default_factory=list)


def family(*names: str) -> Predicate:
    return lambda job: job.family in names


def sector(*names: str) -> Predicate:
    return lambda job: job.sector in names


def skill(*names: str) -> Predicate:
    return lambda job: all(n in job.fields["skills"] for n in names)


def city(*names: str) -> Predicate:
    return lambda job: job.fields["location"] in names


def remote(job: SyntheticJob) -> bool:
    return bool(job.fields["remote"])


def kind(name: str) -> Predicate:
    return lambda job: job.fields["job_type"] == name


def both(*predicates: Predicate) -> Predicate:
    return lambda job: all(p(job) for p in predicates)


TOPIC: list[tuple[str, str, Predicate]] = [
    ("backend developer internship", "software", family("backend")),
    ("build APIs and tune database queries", "software", family("backend")),
    ("I enjoy making web pages look and feel good", "software", family("frontend")),
    ("react developer", "software", skill("React")),
    ("work on both the browser and the server", "software", family("fullstack")),
    ("making phone apps", "software", family("mobile")),
    ("android kotlin", "software", skill("Kotlin")),
    ("keep servers running and automate deployments", "fulltime", family("devops")),
    ("kubernetes and terraform", "fulltime", skill("Kubernetes")),
    ("build data pipelines and warehouses", "data", family("data_engineering")),
    ("apache spark jobs", "data", skill("Spark")),
    ("forecasting and experiments with statistics", "data", family("data_science")),
    ("dashboards and reports for business teams", "data", family("analytics")),
    ("training neural networks for production", "ml", family("ml")),
    ("large language models and chatbots", "ml", family("nlp")),
    ("teach computers to understand images", "ml", family("vision")),
    ("object detection in video", "ml", family("vision")),
    ("ethical hacking", "software", family("security")),
    ("software testing automation", "software", family("qa")),
    ("firmware for microcontrollers", "electronics", family("embedded")),
    ("chip design verilog", "electronics", family("vlsi")),
    ("digital logic verification before tape-out", "electronics", family("vlsi")),
    ("robots that move in warehouses", "mechanical", family("robotics")),
    ("CAD modelling of mechanical parts", "mechanical", family("mechanical")),
    ("fluid flow simulation", "mechanical", family("thermal")),
    ("factory operations and process improvement", "mechanical", family("manufacturing")),
    ("solar power and the electricity grid", "electronics", family("electrical")),
    ("bridge and building design", "civil", family("civil")),
    ("chemical plant process design", "mechanical", family("chemical")),
    ("user research and wireframes", "product", family("design")),
    ("deciding product features and writing specs", "product", family("product")),
    ("stock market and trading research", "data", family("finance")),
    ("smart contracts", "software", family("blockchain")),
]

CONSTRAINT: list[tuple[str, str, Predicate]] = [
    (
        "machine learning in healthcare",
        "ml",
        both(family("ml", "nlp", "vision"), sector("healthcare")),
    ),
    ("jobs with farmers and crops", "ml", sector("agriculture")),
    ("electric vehicle companies", "mechanical", sector("mobility")),
    ("satellite company roles", "electronics", sector("space")),
    ("game studio", "software", sector("gaming")),
    ("carbon emissions and climate work", "mechanical", sector("climate")),
    ("education technology", "product", sector("education")),
    ("payments startup engineering", "software", sector("fintech")),
    ("internship in Pune", "software", both(city("Pune"), kind("internship"))),
    ("jobs in Chennai", "mechanical", city("Chennai")),
    (
        "Hyderabad software roles",
        "fulltime",
        both(
            city("Hyderabad"), family("backend", "frontend", "fullstack", "mobile", "devops", "qa")
        ),
    ),
    ("remote data science", "data", both(family("data_science", "analytics"), remote)),
    ("remote frontend internship", "software", both(family("frontend", "fullstack"), remote)),
    ("full-time devops engineer", "fulltime", both(family("devops"), kind("full-time"))),
    ("full-time data engineer", "data", both(family("data_engineering"), kind("full-time"))),
    (
        "python and statistics internship",
        "data",
        both(skill("Python", "Statistics"), kind("internship")),
    ),
    (
        "C++ roles in robotics or vision",
        "electronics",
        both(family("robotics", "vision"), skill("C++")),
    ),
    ("matlab internships", "mechanical", both(skill("MATLAB"), kind("internship"))),
    ("docker and aws", "fulltime", skill("Docker", "AWS")),
    (
        "logistics company automation",
        "mechanical",
        both(sector("logistics"), family("robotics", "vision", "devops", "qa")),
    ),
]

# Vague queries; the profile decides.
PERSONAL: list[tuple[str, str, tuple[str, ...]]] = [
    ("software internships for me", "software", ("backend", "fullstack", "frontend")),
    ("web development internship", "software", ("frontend", "fullstack", "backend")),
    ("python developer internship", "software", ("backend", "qa", "fullstack")),
    ("internship where I can use my skills", "software", ("backend", "fullstack")),
    ("AI internships", "ml", ("ml", "nlp", "vision")),
    ("deep learning internship", "ml", ("ml", "nlp", "vision")),
    ("research internship in machine intelligence", "ml", ("nlp", "vision", "ml")),
    ("something with models and data", "ml", ("ml", "nlp", "data_science")),
    ("analyst roles near Delhi", "data", ("analytics", "data_science", "finance")),
    ("jobs working with numbers", "data", ("analytics", "data_science", "finance")),
    ("business data roles", "data", ("analytics", "data_science", "data_engineering")),
    ("hardware roles", "electronics", ("embedded", "vlsi")),
    ("electronics core jobs", "electronics", ("embedded", "vlsi", "electrical")),
    ("chip or board level work", "electronics", ("vlsi", "embedded")),
    ("core mechanical openings", "mechanical", ("mechanical", "thermal", "manufacturing")),
    ("design engineer openings", "mechanical", ("mechanical", "thermal")),
    ("simulation engineer", "mechanical", ("thermal", "mechanical")),
    ("core civil openings", "civil", ("civil",)),
    ("site and structure work", "civil", ("civil",)),
    ("non-coding internships", "product", ("product", "design")),
    ("internship talking to users", "product", ("design", "product")),
    ("backend or infrastructure job", "fulltime", ("backend", "devops")),
    ("cloud job after graduation", "fulltime", ("devops", "backend", "data_engineering")),
    (
        "permanent engineering role",
        "fulltime",
        ("backend", "devops", "fullstack", "data_engineering"),
    ),
]


def _facts(job: SyntheticJob) -> JobFacts:
    f = job.fields
    return JobFacts(
        title=f["title"],
        skills=f["skills"],
        location=f["location"],
        remote=f["remote"],
        job_type=f["job_type"],
        stipend_min=f["stipend_min"],
        stipend_max=f["stipend_max"],
        duration_months=f["duration_months"],
    )


def _suits(job: SyntheticJob, profile: dict[str, Any], families: tuple[str, ...]) -> bool:
    """Right topic, allowed type, acceptable place, and at least a third of the skills."""
    prefs = Preferences.from_dict(profile["preferences"])
    facts = _facts(job)
    if job.family not in families or facts.job_type not in prefs.job_types:
        return False
    matched, _ = skill_overlap(facts.skills, profile["skills"])
    return location_match(facts, prefs) and len(matched) * 3 >= len(facts.skills)


def build_cases(jobs: list[SyntheticJob]) -> list[Case]:
    cases = []
    for slice_name, rows in (("topic", TOPIC), ("constraint", CONSTRAINT)):
        for query, profile, predicate in rows:
            relevant = [j.key for j in jobs if predicate(j)]
            cases.append(Case(query, profile, slice_name, relevant))
    for query, profile, families in PERSONAL:
        relevant = [j.key for j in jobs if _suits(j, PROFILES[profile], families)]
        cases.append(Case(query, profile, "personal", relevant))
    return [c for c in cases if c.relevant]
