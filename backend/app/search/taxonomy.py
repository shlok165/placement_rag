"""Shared vocabulary: skills, role families and locations, with their aliases."""

import re
from collections.abc import Iterable
from functools import lru_cache

# Canonical skill -> aliases (lower case).
SKILLS: dict[str, tuple[str, ...]] = {
    "Python": ("python3", "py"),
    "Java": (),
    "C++": ("cpp", "c plus plus"),
    "C": ("c language", "embedded c"),
    "C#": ("csharp", ".net", "dotnet"),
    "Go": ("golang",),
    "Rust": (),
    "JavaScript": ("js", "es6"),
    "TypeScript": ("ts",),
    "Kotlin": (),
    "Swift": (),
    "Scala": (),
    "R": ("r language", "r programming"),
    "MATLAB": ("simulink",),
    "SQL": ("mysql", "postgresql", "postgres", "sqlite"),
    "NoSQL": ("mongodb", "cassandra", "dynamodb"),
    "React": ("react.js", "reactjs"),
    "Angular": (),
    "Vue": ("vue.js", "vuejs"),
    "Next.js": ("nextjs",),
    "Node.js": ("node", "nodejs", "express.js", "express"),
    "HTML": ("html5",),
    "CSS": ("css3", "tailwind", "tailwind css"),
    "Django": (),
    "Flask": (),
    "FastAPI": (),
    "Spring Boot": ("spring", "springboot"),
    "REST APIs": ("rest", "rest api", "restful apis", "restful"),
    "GraphQL": (),
    "gRPC": (),
    "Microservices": ("microservice",),
    "Docker": ("containers", "containerization"),
    "Kubernetes": ("k8s",),
    "AWS": ("amazon web services", "ec2", "s3"),
    "Azure": (),
    "GCP": ("google cloud",),
    "Terraform": ("infrastructure as code",),
    "CI/CD": ("jenkins", "github actions", "continuous integration"),
    "Linux": ("unix", "bash", "shell scripting"),
    "Git": ("github", "version control"),
    "Kafka": ("apache kafka",),
    "Redis": (),
    "Spark": ("apache spark", "pyspark"),
    "Airflow": ("apache airflow",),
    "Data Structures": ("dsa", "data structures and algorithms", "algorithms"),
    "Operating Systems": (),
    "Computer Networks": ("networking", "tcp/ip"),
    "System Design": ("distributed systems",),
    "Machine Learning": ("ml", "scikit-learn", "sklearn"),
    "Deep Learning": ("neural networks",),
    "PyTorch": ("torch",),
    "TensorFlow": ("keras",),
    "NLP": ("natural language processing", "transformers", "llm", "llms", "hugging face"),
    "Computer Vision": ("opencv", "image processing"),
    "Reinforcement Learning": (),
    "MLOps": ("mlflow",),
    "Statistics": ("probability", "hypothesis testing", "a/b testing"),
    "Pandas": ("numpy",),
    "Data Visualization": ("tableau", "power bi", "matplotlib"),
    "Excel": ("spreadsheets", "ms excel"),
    "Verilog": ("systemverilog", "vhdl", "rtl"),
    "VLSI": ("asic", "physical design"),
    "FPGA": (),
    "Embedded Systems": ("microcontrollers", "arduino", "stm32", "firmware", "rtos"),
    "PCB Design": ("altium", "kicad"),
    "Signal Processing": ("dsp",),
    "Control Systems": ("pid control",),
    "ROS": ("robot operating system",),
    "Power Systems": ("power electronics",),
    "IoT": ("internet of things", "mqtt"),
    "SolidWorks": ("solid works",),
    "AutoCAD": ("auto cad",),
    "CATIA": (),
    "ANSYS": ("fea", "finite element analysis"),
    "CFD": ("computational fluid dynamics", "openfoam"),
    "Manufacturing": ("cnc", "lean manufacturing", "six sigma"),
    "Thermodynamics": ("heat transfer",),
    "STAAD Pro": ("structural analysis", "etabs"),
    "GIS": ("arcgis", "qgis"),
    "Aspen Plus": ("process simulation", "aspen hysys"),
    "Figma": ("wireframing", "prototyping"),
    "User Research": ("usability testing", "ux research"),
    "Product Management": ("product roadmap", "roadmapping"),
    "Financial Modeling": ("financial modelling", "valuation"),
    "Market Research": ("competitor analysis",),
    "Communication": ("presentation skills", "stakeholder management"),
    "Cybersecurity": ("information security", "penetration testing", "owasp"),
    "Cryptography": (),
    "Blockchain": ("solidity", "smart contracts"),
    "Android": ("android development", "jetpack compose"),
    "iOS": ("ios development", "swiftui"),
    "Flutter": ("dart",),
    "React Native": (),
    "Testing": ("selenium", "unit testing", "test automation", "pytest"),
    "Technical Writing": ("documentation",),
}

# Role family -> phrases that identify it in a title or a preference.
ROLES: dict[str, tuple[str, ...]] = {
    "Software Engineering": ("software engineer", "sde", "software developer", "software"),
    "Backend": ("backend", "back end", "back-end", "server side", "api developer"),
    "Frontend": ("frontend", "front end", "front-end", "ui developer", "web developer"),
    "Full Stack": ("full stack", "fullstack", "full-stack"),
    "Mobile": ("android", "ios", "mobile", "flutter"),
    "DevOps and Cloud": ("devops", "site reliability", "sre", "cloud engineer", "platform"),
    "Data Engineering": ("data engineer", "data platform", "etl"),
    "Data Science": ("data scientist", "data science", "applied scientist"),
    "Data Analytics": ("data analyst", "business analyst", "analytics", "business intelligence"),
    "Machine Learning": ("machine learning", "ml engineer", "deep learning", "ai engineer", "nlp"),
    "Computer Vision": ("computer vision", "perception", "imaging"),
    "Security": ("security", "penetration", "cyber"),
    "Quality Assurance": ("qa", "test engineer", "sdet", "quality assurance"),
    "Embedded": ("embedded", "firmware", "iot"),
    "VLSI": ("vlsi", "rtl", "asic", "chip", "hardware design", "design verification"),
    "Robotics": ("robotics", "autonomous", "controls engineer"),
    "Mechanical Design": ("mechanical", "cad", "product design engineer"),
    "Manufacturing": ("manufacturing", "production engineer", "process engineer", "industrial"),
    "Electrical": ("electrical", "power systems", "power electronics"),
    "Civil": ("civil", "structural", "geotechnical", "construction"),
    "Chemical": ("chemical", "process simulation"),
    "Design": ("ux", "ui/ux", "product designer", "interaction design"),
    "Product": ("product manager", "product management", "associate product"),
    "Finance": ("finance", "quant", "investment", "equity research", "risk analyst"),
    "Consulting": ("consultant", "consulting", "strategy"),
    "Research": ("research intern", "research engineer", "research assistant"),
}

LOCATIONS = (
    "Bengaluru",
    "Hyderabad",
    "Pune",
    "Mumbai",
    "Delhi",
    "Gurugram",
    "Noida",
    "Chennai",
    "Kolkata",
    "Ahmedabad",
    "Chandigarh",
    "Mohali",
    "Jaipur",
    "Kochi",
    "Coimbatore",
    "Ropar",
)
LOCATION_ALIASES = {
    "bangalore": "Bengaluru",
    "blr": "Bengaluru",
    "gurgaon": "Gurugram",
    "new delhi": "Delhi",
    "bombay": "Mumbai",
    "madras": "Chennai",
    "calcutta": "Kolkata",
    "rupnagar": "Ropar",
    "cochin": "Kochi",
}


def _term_pattern(term: str) -> str:
    # Letters, digits and + # around a term mean it is part of another word ("Go" in "Good").
    return rf"(?<![A-Za-z0-9+#.]){re.escape(term)}(?![A-Za-z0-9+#]|\.[A-Za-z0-9])"


@lru_cache
def _alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for canonical, aliases in SKILLS.items():
        mapping[canonical.lower()] = canonical
        for alias in aliases:
            mapping.setdefault(alias, canonical)
    return mapping


# Too short or too common in prose to be trusted outside a skills list.
_AMBIGUOUS = {"c", "r", "go", "py", "ts", "node", "spring", "express", "rest", "s3", "swift"}
_AMBIGUOUS |= {"spark", "rust", "containers", "networking", "algorithms", "probability", "ml"}
_AMBIGUOUS |= {"transformers", "documentation", "dart", "testing", "communication", "scala"}


@lru_cache
def _skill_regex(strict: bool) -> re.Pattern[str]:
    terms = [t for t in _alias_map() if not (strict and t in _AMBIGUOUS)]
    terms.sort(key=len, reverse=True)
    return re.compile("|".join(_term_pattern(t) for t in terms), re.IGNORECASE)


# Ambiguous skills still count in prose when written the way a technology is written.
_CASED = {"Go": "Go", "Spark": "Spark", "Rust": "Rust", "Swift": "Swift", "Scala": "Scala"}
_CASED |= {
    "ML": "Machine Learning",
    "REST": "REST APIs",
    "Node": "Node.js",
    "Spring": "Spring Boot",
}
_CASED_REGEX = re.compile("|".join(_term_pattern(t) for t in _CASED))


def canonical_skill(value: str) -> str:
    cleaned = " ".join(value.split()).strip(" .;,•-")
    return _alias_map().get(cleaned.lower(), cleaned)


def canonical_skills(values: Iterable[str]) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        skill = canonical_skill(value)
        if skill and len(skill) <= 60:
            seen.setdefault(skill.lower(), skill)
    return list(seen.values())


def skills_in_text(text: str) -> list[str]:
    """Skills mentioned in free text, in order of first appearance."""
    hits = [(m.start(), _alias_map()[m.group().lower()]) for m in _skill_regex(True).finditer(text)]
    hits += [(m.start(), _CASED[m.group()]) for m in _CASED_REGEX.finditer(text)]
    return list(dict.fromkeys(skill for _, skill in sorted(hits)))


def roles_in_text(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for role, phrases in ROLES.items():
        terms = (role.lower(), *phrases)
        if any(re.search(_term_pattern(term), lowered) for term in terms):
            found.append(role)
    return found


def canonical_location(value: str) -> str:
    cleaned = " ".join(value.split()).strip(" .,;")
    lowered = cleaned.lower()
    if lowered in LOCATION_ALIASES:
        return LOCATION_ALIASES[lowered]
    for location in LOCATIONS:
        if lowered == location.lower():
            return location
    return cleaned


def locations_in_text(text: str) -> list[str]:
    lowered = text.lower()
    found: dict[str, int] = {}
    for term, canonical in [*((x.lower(), x) for x in LOCATIONS), *LOCATION_ALIASES.items()]:
        match = re.search(_term_pattern(term), lowered)
        if match:
            found[canonical] = min(match.start(), found.get(canonical, match.start()))
    return sorted(found, key=lambda name: found[name])
