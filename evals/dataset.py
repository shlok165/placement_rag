"""Deterministic synthetic postings. Same seed, same output. No real companies or people."""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

SEED = 20260101
REFERENCE_DATE = date(2026, 1, 1)
JOBS_PER_FAMILY = 6


@dataclass(frozen=True)
class Family:
    key: str
    titles: tuple[str, ...]
    # Sentences describe the work in plain words, so wording often differs from the title.
    work: tuple[str, ...]
    core: tuple[str, ...]
    extra: tuple[str, ...]
    full_time_share: float = 0.35


FAMILIES: tuple[Family, ...] = (
    Family(
        "backend",
        ("Backend Engineering Intern", "Server-Side Developer", "API Developer Intern"),
        (
            "Design endpoints that other teams call thousands of times a minute.",
            "Tune slow database queries and keep response times predictable.",
            "Write services that stay correct when traffic spikes.",
            "Own a small service from design review to on-call handover.",
        ),
        ("Python", "SQL", "REST APIs"),
        ("FastAPI", "Django", "Redis", "Docker", "Kafka", "Microservices"),
    ),
    Family(
        "frontend",
        ("Frontend Developer Intern", "UI Engineer", "Web Developer Intern"),
        (
            "Build the screens customers use every day and keep them fast on slow phones.",
            "Turn design files into accessible, reusable components.",
            "Reduce page load time and fix layout bugs across browsers.",
            "Work with designers on interactions that feel effortless.",
        ),
        ("JavaScript", "React", "CSS"),
        ("TypeScript", "HTML", "Next.js", "Testing", "Figma", "GraphQL"),
    ),
    Family(
        "fullstack",
        ("Full Stack Developer Intern", "Full Stack Engineer", "Product Engineer Intern"),
        (
            "Ship complete features, from the database table to the button on the page.",
            "Prototype with customers on Monday and release on Friday.",
            "Maintain an internal tool used by the operations team.",
            "Connect third-party payment and messaging providers.",
        ),
        ("JavaScript", "Node.js", "React"),
        ("SQL", "NoSQL", "Docker", "TypeScript", "REST APIs", "Git"),
    ),
    Family(
        "mobile",
        ("Android Developer Intern", "Mobile App Developer", "Flutter Developer Intern"),
        (
            "Build app screens that work offline in areas with patchy networks.",
            "Cut start-up time and battery use on low-end handsets.",
            "Release to the app store every two weeks.",
            "Add push notifications and in-app guidance for first-time users.",
        ),
        ("Android", "Kotlin"),
        ("Flutter", "Java", "REST APIs", "Git", "iOS", "React Native"),
    ),
    Family(
        "devops",
        ("DevOps Engineer Intern", "Site Reliability Engineer", "Cloud Platform Intern"),
        (
            "Automate releases so that engineers deploy without fear.",
            "Keep clusters healthy and bills under control.",
            "Build dashboards and alerts that point to the cause of an outage.",
            "Replace hand-run scripts with repeatable infrastructure.",
        ),
        ("Linux", "Docker", "Kubernetes"),
        ("AWS", "Terraform", "CI/CD", "Python", "GCP", "Git"),
    ),
    Family(
        "data_engineering",
        ("Data Engineer Intern", "Data Platform Engineer", "ETL Developer Intern"),
        (
            "Move billions of events from apps to a warehouse every day.",
            "Model tables that analysts can trust without asking.",
            "Add checks that catch broken feeds before anyone notices.",
            "Migrate nightly batch jobs to streaming pipelines.",
        ),
        ("Python", "SQL", "Spark"),
        ("Airflow", "Kafka", "AWS", "Scala", "NoSQL", "Docker"),
    ),
    Family(
        "data_science",
        ("Data Science Intern", "Data Scientist", "Applied Scientist Intern"),
        (
            "Predict demand so that shelves are stocked before customers arrive.",
            "Design experiments and explain the results to people who do not like statistics.",
            "Build risk scores and track how they drift over time.",
            "Segment users and suggest what to offer each group.",
        ),
        ("Python", "Statistics", "Machine Learning"),
        ("Pandas", "SQL", "Data Visualization", "R", "Spark"),
    ),
    Family(
        "analytics",
        ("Business Analyst Intern", "Data Analyst", "Business Intelligence Intern"),
        (
            "Answer weekly questions from leadership with clear charts.",
            "Find where customers drop off and what it costs.",
            "Maintain reports that the sales team opens every morning.",
            "Clean messy spreadsheets and turn them into a single source of truth.",
        ),
        ("SQL", "Excel", "Data Visualization"),
        ("Python", "Statistics", "Communication", "Pandas", "Market Research"),
    ),
    Family(
        "ml",
        ("Machine Learning Engineer Intern", "ML Engineer", "AI Engineer Intern"),
        (
            "Train models that learn from user behaviour and put them behind a fast service.",
            "Shorten the path from notebook to production.",
            "Monitor predictions and retrain when the world changes.",
            "Compress large models so they fit on small devices.",
        ),
        ("Python", "Machine Learning", "PyTorch"),
        ("Deep Learning", "MLOps", "TensorFlow", "Docker", "SQL", "AWS"),
    ),
    Family(
        "nlp",
        ("NLP Research Intern", "Language AI Engineer", "Conversational AI Intern"),
        (
            "Help software understand questions written in Hindi, Punjabi and English.",
            "Summarise long documents without inventing facts.",
            "Build assistants that answer from a company's own files.",
            "Measure how often generated text is wrong, and reduce it.",
        ),
        ("Python", "NLP", "Deep Learning"),
        ("PyTorch", "Machine Learning", "Statistics", "FastAPI"),
    ),
    Family(
        "vision",
        ("Computer Vision Intern", "Perception Engineer", "Imaging Research Intern"),
        (
            "Teach cameras to spot defects that people miss on a production line.",
            "Detect and track objects in video from moving vehicles.",
            "Read handwritten forms and damaged labels.",
            "Estimate crop health from drone pictures.",
        ),
        ("Python", "Computer Vision", "Deep Learning"),
        ("PyTorch", "C++", "Machine Learning", "ROS"),
    ),
    Family(
        "security",
        ("Cybersecurity Intern", "Security Analyst", "Application Security Intern"),
        (
            "Find weaknesses in our products before attackers do.",
            "Investigate suspicious logins and write clear incident reports.",
            "Help developers fix risky code patterns.",
            "Run phishing drills and measure whether they help.",
        ),
        ("Cybersecurity", "Computer Networks", "Linux"),
        ("Python", "Cryptography", "AWS", "Testing"),
    ),
    Family(
        "qa",
        ("QA Automation Intern", "Software Test Engineer", "SDET Intern"),
        (
            "Write checks that run on every change and fail for good reasons.",
            "Reproduce customer bugs and reduce them to small cases.",
            "Plan release testing and decide what is safe to skip.",
            "Cut flaky runs so that engineers trust the results.",
        ),
        ("Testing", "Python"),
        ("Java", "CI/CD", "SQL", "Git", "REST APIs"),
    ),
    Family(
        "embedded",
        ("Embedded Systems Intern", "Firmware Engineer", "IoT Engineer Intern"),
        (
            "Write low-level code for battery-powered sensors.",
            "Bring up new boards and debug them with a logic analyser.",
            "Stretch a coin cell to last five years in the field.",
            "Update devices over the air without bricking them.",
        ),
        ("C", "Embedded Systems"),
        ("C++", "IoT", "PCB Design", "Linux", "Python", "Signal Processing"),
    ),
    Family(
        "vlsi",
        ("VLSI Design Intern", "RTL Design Engineer", "Design Verification Intern"),
        (
            "Describe digital blocks and prove that they meet timing.",
            "Build test benches that find corner cases before tape-out.",
            "Reduce area and leakage in a memory controller.",
            "Script the flow from netlist to layout checks.",
        ),
        ("Verilog", "VLSI"),
        ("FPGA", "Python", "C++", "Linux", "Signal Processing"),
        0.45,
    ),
    Family(
        "robotics",
        ("Robotics Intern", "Autonomous Systems Engineer", "Controls Engineer Intern"),
        (
            "Help warehouse machines plan paths around people.",
            "Tune motion so that arms stop without overshoot.",
            "Fuse readings from lidar and wheels to know where the machine is.",
            "Test in simulation, then on the real floor the same week.",
        ),
        ("ROS", "C++", "Control Systems"),
        ("Python", "Computer Vision", "MATLAB", "Embedded Systems"),
    ),
    Family(
        "mechanical",
        ("Mechanical Design Intern", "CAD Engineer", "Product Design Engineer Intern"),
        (
            "Model parts that are light, strong and cheap to make.",
            "Run stress checks and improve brackets that crack in the field.",
            "Draw assemblies that a workshop can build without phone calls.",
            "Compare materials for a frame that must survive monsoon roads.",
        ),
        ("SolidWorks", "ANSYS"),
        ("AutoCAD", "CATIA", "Thermodynamics", "MATLAB", "Manufacturing"),
    ),
    Family(
        "thermal",
        ("CFD Analyst Intern", "Thermal Engineer", "Aerodynamics Intern"),
        (
            "Simulate air flow around vehicles and suggest shape changes.",
            "Keep battery packs cool during fast charging.",
            "Validate simulations against wind-tunnel data.",
            "Size heat exchangers for a compact plant.",
        ),
        ("CFD", "Thermodynamics"),
        ("ANSYS", "MATLAB", "Python", "SolidWorks"),
    ),
    Family(
        "manufacturing",
        ("Manufacturing Engineer Intern", "Production Engineer", "Industrial Engineering Intern"),
        (
            "Remove bottlenecks on an assembly line of forty stations.",
            "Cut scrap by finding the machine setting that drifts.",
            "Plan shifts and stock so that orders leave on time.",
            "Introduce visual checks that stop defects early.",
        ),
        ("Manufacturing",),
        ("AutoCAD", "Excel", "Statistics", "SolidWorks", "Communication"),
        0.45,
    ),
    Family(
        "electrical",
        ("Power Systems Intern", "Electrical Engineer", "Power Electronics Intern"),
        (
            "Study how rooftop solar affects the local grid.",
            "Design converters that waste less energy as heat.",
            "Protect substations against faults and test relay settings.",
            "Model motor drives for two-wheelers.",
        ),
        ("Power Systems", "MATLAB"),
        ("PCB Design", "Control Systems", "AutoCAD", "Embedded Systems"),
    ),
    Family(
        "civil",
        ("Structural Engineering Intern", "Civil Engineer", "Geotechnical Intern"),
        (
            "Check beams and slabs for a hospital block.",
            "Survey sites and map soil conditions for a highway.",
            "Estimate quantities and follow progress on site.",
            "Assess old bridges and recommend repairs.",
        ),
        ("STAAD Pro", "AutoCAD"),
        ("GIS", "Excel", "MATLAB", "Communication"),
        0.45,
    ),
    Family(
        "chemical",
        ("Process Engineering Intern", "Chemical Engineer", "Process Simulation Intern"),
        (
            "Model a distillation column and cut its steam use.",
            "Scale a reaction from the lab bench to a pilot plant.",
            "Review safety studies and close open actions.",
            "Recover solvent that is currently burned.",
        ),
        ("Aspen Plus", "Thermodynamics"),
        ("MATLAB", "Python", "Excel", "Manufacturing"),
    ),
    Family(
        "design",
        ("UX Design Intern", "Product Designer", "Interaction Design Intern"),
        (
            "Talk to users, sketch ideas and test them before anyone writes code.",
            "Simplify a form that half of visitors abandon.",
            "Look after a shared library of components and patterns.",
            "Make our app easier for people who use a screen reader.",
        ),
        ("Figma", "User Research"),
        ("HTML", "CSS", "Communication"),
    ),
    Family(
        "product",
        ("Associate Product Manager", "Product Management Intern", "Product Strategy Intern"),
        (
            "Decide what to build next and explain why.",
            "Write crisp specs and follow them through launch.",
            "Turn support tickets into a ranked list of problems.",
            "Size a new market and propose a first release.",
        ),
        ("Product Management", "Communication"),
        ("SQL", "Market Research", "User Research", "Excel", "Data Visualization"),
        0.5,
    ),
    Family(
        "finance",
        ("Quantitative Research Intern", "Investment Analyst", "Risk Analyst Intern"),
        (
            "Test trading ideas on ten years of market data.",
            "Value companies and defend the number in front of partners.",
            "Estimate how much a portfolio could lose on a bad day.",
            "Automate the daily profit and loss report.",
        ),
        ("Financial Modeling", "Statistics"),
        ("Python", "Excel", "SQL", "Communication", "C++"),
    ),
    Family(
        "blockchain",
        ("Blockchain Developer Intern", "Smart Contract Engineer", "Web3 Engineer Intern"),
        (
            "Write contracts that hold real value and have them audited.",
            "Trace tokens across chains and flag odd transfers.",
            "Build wallets that non-technical people can use.",
            "Cut transaction fees by batching writes.",
        ),
        ("Blockchain", "JavaScript"),
        ("Cryptography", "Go", "Node.js", "Rust", "Testing"),
    ),
)

# Sector -> what the company does, phrased without role words.
SECTORS: dict[str, str] = {
    "healthcare": "We help hospitals and clinics diagnose patients earlier.",
    "agriculture": "We work with farmers to raise yields and cut waste.",
    "fintech": "We make payments and lending simpler for small shops.",
    "education": "We build learning products for school and college students.",
    "mobility": "We make electric two-wheelers and the charging network behind them.",
    "climate": "We measure and reduce carbon emissions for factories.",
    "logistics": "We move parcels between six hundred towns every night.",
    "retail": "We run online stores for local brands.",
    "space": "We build small satellites and the ground stations that talk to them.",
    "gaming": "We make multiplayer games played by two million people a month.",
    "semiconductor": "We design chips for sensors and edge devices.",
    "infrastructure": "We plan and build bridges, metros and water networks.",
}

COMPANY_STEMS = [
    "Aranya",
    "Bluepeak",
    "Cirrusline",
    "Deepvale",
    "Elmfort",
    "Fernhill",
    "Gridwell",
    "Harbourlight",
    "Indusloop",
    "Juniperworks",
    "Kiteway",
    "Lumenfield",
    "Mapleworth",
    "Nimbusone",
    "Orchardlane",
    "Pinecrest",
    "Quartzbay",
    "Riverstone",
    "Saffronhub",
    "Tealbridge",
    "Umberline",
    "Vantagrid",
    "Willowtech",
    "Xenoleaf",
    "Yellowfin",
    "Zephyrnest",
]
COMPANY_SUFFIX = {
    "healthcare": "Health",
    "agriculture": "Agritech",
    "fintech": "Pay",
    "education": "Learning",
    "mobility": "Motors",
    "climate": "Climate",
    "logistics": "Logistics",
    "retail": "Commerce",
    "space": "Space",
    "gaming": "Games",
    "semiconductor": "Semiconductors",
    "infrastructure": "Infra",
}

# Core engineering families work in sectors where they make sense.
FAMILY_SECTORS: dict[str, tuple[str, ...]] = {
    "embedded": ("mobility", "agriculture", "healthcare", "space", "semiconductor"),
    "vlsi": ("semiconductor", "space"),
    "robotics": ("logistics", "agriculture", "mobility", "space"),
    "mechanical": ("mobility", "space", "healthcare", "climate"),
    "thermal": ("mobility", "space", "climate"),
    "manufacturing": ("mobility", "semiconductor", "retail", "healthcare"),
    "electrical": ("mobility", "climate", "infrastructure"),
    "civil": ("infrastructure",),
    "chemical": ("climate", "healthcare"),
    "finance": ("fintech",),
    "blockchain": ("fintech", "gaming", "logistics"),
    "vision": ("healthcare", "agriculture", "logistics", "mobility", "semiconductor"),
    "nlp": ("education", "healthcare", "fintech", "retail"),
}
OFFICE_SECTORS = (
    "healthcare",
    "agriculture",
    "fintech",
    "education",
    "logistics",
    "retail",
    "gaming",
    "climate",
)
CITIES = (
    "Bengaluru",
    "Hyderabad",
    "Pune",
    "Mumbai",
    "Gurugram",
    "Noida",
    "Chennai",
    "Delhi",
    "Chandigarh",
)
REMOTE_FAMILIES = {
    "backend",
    "frontend",
    "fullstack",
    "mobile",
    "devops",
    "data_engineering",
    "data_science",
    "analytics",
    "ml",
    "nlp",
    "security",
    "qa",
    "design",
    "product",
    "blockchain",
}
CLOSERS = (
    "You will have a mentor and a clear project from the first week.",
    "The team is small, so your work will be visible.",
    "Good interns are considered for a return offer.",
    "We review work weekly and write things down.",
)


@dataclass
class SyntheticJob:
    key: str
    family: str
    sector: str
    fields: dict[str, Any] = field(default_factory=dict)


def _pay(rng: random.Random, job_type: str) -> tuple[int, int]:
    if job_type == "internship":
        low = rng.randrange(15, 75, 5) * 1_000
        return low, low + rng.choice((0, 5_000, 10_000, 15_000))
    low = rng.randrange(8, 26) * 100_000
    return low, low + rng.choice((2, 4, 6)) * 100_000


def generate_jobs(reference: date = REFERENCE_DATE) -> list[SyntheticJob]:
    rng = random.Random(SEED)
    jobs: list[SyntheticJob] = []
    for family in FAMILIES:
        sectors = FAMILY_SECTORS.get(family.key, OFFICE_SECTORS)
        for index in range(JOBS_PER_FAMILY):
            sector = sectors[(index + rng.randrange(len(sectors))) % len(sectors)]
            title = family.titles[index % len(family.titles)]
            is_full_time = "Intern" not in title or rng.random() < family.full_time_share * 0.3
            job_type = "full-time" if is_full_time else "internship"
            if job_type == "full-time":
                title = title.replace(" Intern", "")
            company = f"{rng.choice(COMPANY_STEMS)} {COMPANY_SUFFIX[sector]}"
            remote = family.key in REMOTE_FAMILIES and rng.random() < 0.3
            location = "" if remote and rng.random() < 0.5 else rng.choice(CITIES)
            skills = [*family.core, *rng.sample(family.extra, k=min(3, len(family.extra)))]
            low, high = _pay(rng, job_type)
            months = rng.choice((2, 3, 6)) if job_type == "internship" else None
            work = rng.sample(family.work, k=3)
            key = f"{family.key}-{index + 1}"
            description = " ".join([SECTORS[sector], *work, rng.choice(CLOSERS)])
            year = rng.choice(("pre-final year", "final year", "any year"))
            jobs.append(
                SyntheticJob(
                    key,
                    family.key,
                    sector,
                    {
                        "company": company,
                        "title": title,
                        "description": description,
                        "requirements": f"Open to {year} B.Tech and M.Tech students.",
                        "skills": skills,
                        "location": location,
                        "remote": remote,
                        "job_type": job_type,
                        "stipend_min": low,
                        "stipend_max": high,
                        "duration_months": months,
                        "deadline": reference + timedelta(days=rng.randrange(4, 75)),
                        "apply_url": f"https://careers.example.com/{key}",
                    },
                )
            )
    return jobs
