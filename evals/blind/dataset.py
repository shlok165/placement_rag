"""Blind postings: another seed, other titles and wording, other sector and city mixes."""

from evals.dataset import Variant

BLIND_SEED = 20261126

TEXT: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "backend": (
        ("Platform Services Intern", "Software Engineer, Core Services"),
        (
            "Keep the order and billing services fast under heavy load.",
            "Add caching where the same records are read again and again.",
            "Split a large codebase into services that deploy on their own.",
            "Write the contracts other teams use to talk to your service.",
        ),
    ),
    "frontend": (
        ("Web Interface Intern", "Client-Side Engineer"),
        (
            "Build the pages shoppers see first and make them load in under a second.",
            "Keep the component library consistent and easy to use with a keyboard.",
            "Hunt down rendering bugs that only show up on older browsers.",
            "Pair with designers to turn sketches into working screens.",
        ),
    ),
    "fullstack": (
        ("Software Generalist Intern", "Founding Engineer"),
        (
            "Own a feature from the schema change to the last pixel.",
            "Talk to early customers and ship what they ask for within days.",
            "Glue together the admin panel, the public site and the database.",
            "Wire up sign-in, payments and email in one small product.",
        ),
    ),
    "mobile": (
        ("App Developer Intern", "Android Engineer"),
        (
            "Ship features to an app installed on millions of phones.",
            "Make the app work offline and sync when the network returns.",
            "Cut app start time and battery use on budget handsets.",
            "Release builds to the store every two weeks.",
        ),
    ),
    "devops": (
        ("Infrastructure Intern", "Reliability Engineer"),
        (
            "Automate how code goes from a merge to production.",
            "Watch dashboards, fix alerts and write the incident notes.",
            "Move workloads between cloud accounts without downtime.",
            "Keep clusters patched, sized and cheap to run.",
        ),
    ),
    "data_engineering": (
        ("Data Pipeline Intern", "Analytics Engineer"),
        (
            "Move raw events into clean tables that analysts trust.",
            "Schedule nightly batch jobs and fix them when they break.",
            "Model the warehouse so reports stay quick as data grows.",
            "Stream sensor readings into storage in near real time.",
        ),
    ),
    "data_science": (
        ("Decision Science Intern", "Research Data Scientist"),
        (
            "Run controlled tests and tell the team which change worked.",
            "Predict demand for next month from past sales.",
            "Explain model results to people who do not code.",
            "Find patterns in customer behaviour with careful statistics.",
        ),
    ),
    "analytics": (
        ("Insights Analyst Intern", "Reporting Analyst"),
        (
            "Answer weekly business questions with queries and charts.",
            "Keep the sales and marketing dashboards correct.",
            "Present findings to managers in short, clear slides.",
            "Clean messy spreadsheets before anyone uses them.",
        ),
    ),
    "ml": (
        ("Applied AI Intern", "Model Engineer"),
        (
            "Train recommendation models and put them behind an API.",
            "Track experiments and retrain models when data drifts.",
            "Make inference cheaper without losing accuracy.",
            "Label data, train, evaluate and repeat until it is good enough.",
        ),
    ),
    "nlp": (
        ("Text AI Intern", "Speech and Language Engineer"),
        (
            "Fine-tune language models to answer customer questions.",
            "Build search over documents written in several Indian languages.",
            "Measure how often the assistant gives a wrong answer.",
            "Turn call transcripts into summaries and tags.",
        ),
    ),
    "vision": (
        ("Visual AI Intern", "Camera Algorithms Engineer"),
        (
            "Spot defects on a production line from camera images.",
            "Count and track objects in traffic footage.",
            "Segment medical scans so doctors can review them faster.",
            "Run image models on small devices at the edge.",
        ),
    ),
    "security": (
        ("Security Operations Intern", "Penetration Tester"),
        (
            "Probe our apps for weaknesses before attackers do.",
            "Review alerts and decide which ones are real threats.",
            "Harden servers and write the rules for access.",
            "Teach developers to avoid common security mistakes.",
        ),
    ),
    "qa": (
        ("Quality Engineering Intern", "Test Automation Engineer"),
        (
            "Write automated checks that run on every code change.",
            "Find bugs before customers do and report them clearly.",
            "Build test data and environments for the release team.",
            "Measure flaky tests and make them reliable.",
        ),
    ),
    "embedded": (
        ("Firmware Intern", "Embedded Software Engineer"),
        (
            "Write low-level code for sensors that run on batteries for years.",
            "Bring up new circuit boards and debug them with a scope.",
            "Make small connected devices talk to the cloud.",
            "Squeeze features into a few kilobytes of memory.",
        ),
    ),
    "vlsi": (
        ("Silicon Design Intern", "ASIC Verification Engineer"),
        (
            "Write hardware descriptions for blocks inside a chip.",
            "Check designs with simulations before they are manufactured.",
            "Meet timing and power targets for a new processor block.",
            "Prototype logic on programmable boards.",
        ),
    ),
    "robotics": (
        ("Autonomy Intern", "Robot Software Engineer"),
        (
            "Program robot arms that pick and place parcels.",
            "Plan paths for vehicles that drive themselves in a yard.",
            "Tune feedback loops so machines move smoothly.",
            "Fuse camera and lidar data so the robot knows where it is.",
        ),
    ),
    "mechanical": (
        ("Design Engineering Intern", "Mechanical Engineer"),
        (
            "Model parts in 3D and prepare drawings for the workshop.",
            "Run stress analysis on brackets and housings.",
            "Choose materials that are strong, light and affordable.",
            "Build and test prototypes with the shop floor team.",
        ),
    ),
    "thermal": (
        ("Heat Transfer Intern", "Simulation Engineer"),
        (
            "Simulate airflow and cooling inside battery packs.",
            "Study how heat moves through engine parts.",
            "Compare simulated results with wind tunnel tests.",
            "Improve the cooling of electronics enclosures.",
        ),
    ),
    "manufacturing": (
        ("Operations Engineering Intern", "Plant Engineer"),
        (
            "Reduce waste and downtime on an assembly line.",
            "Plan production schedules with the shift supervisors.",
            "Set up quality checks and track defect rates.",
            "Improve how parts move through the factory.",
        ),
    ),
    "electrical": (
        ("Energy Systems Intern", "Grid Engineer"),
        (
            "Design how solar farms connect to the grid.",
            "Size cables, breakers and transformers for new sites.",
            "Build motor drives and battery chargers.",
            "Study power quality on a city distribution network.",
        ),
    ),
    "civil": (
        ("Construction Engineering Intern", "Structural Designer"),
        (
            "Check the design of beams, columns and foundations.",
            "Visit sites and track progress against drawings.",
            "Survey land and plan roads and drains.",
            "Estimate quantities and costs for building projects.",
        ),
    ),
    "chemical": (
        ("Process Development Intern", "Plant Process Engineer"),
        (
            "Simulate reactors and distillation columns.",
            "Make a chemical process safer and use less energy.",
            "Scale a lab recipe up to a pilot plant.",
            "Track yields and fix problems in a running plant.",
        ),
    ),
    "design": (
        ("Experience Design Intern", "Visual and Interaction Designer"),
        (
            "Interview users and turn what you learn into flows.",
            "Sketch, prototype and test screens with real people.",
            "Keep the design system tidy and documented.",
            "Make sure the product is usable by everyone.",
        ),
    ),
    "product": (
        ("Product Operations Intern", "Junior Product Manager"),
        (
            "Decide what the team builds next and explain why.",
            "Write requirements and check that releases meet them.",
            "Study competitors and talk to customers every week.",
            "Track product metrics and suggest improvements.",
        ),
    ),
    "finance": (
        ("Trading Research Intern", "Credit Analyst"),
        (
            "Build pricing models and test them on past data.",
            "Assess the risk of loans and portfolios.",
            "Write research notes on companies and markets.",
            "Automate reports for the investment committee.",
        ),
    ),
    "blockchain": (
        ("Decentralised Apps Intern", "Protocol Engineer"),
        (
            "Write and audit contracts that hold real money.",
            "Build wallets and tools for a public ledger.",
            "Measure gas costs and make transactions cheaper.",
            "Connect on-chain data to ordinary web apps.",
        ),
    ),
}

SECTORS: dict[str, str] = {
    "healthcare": "Our clinics and labs use software to reach patients sooner.",
    "agriculture": "We help growers plan sowing, irrigation and harvest.",
    "fintech": "We run lending and savings products for small businesses.",
    "education": "Our courses and exams reach students in small towns.",
    "mobility": "We build electric scooters, buses and their chargers.",
    "climate": "We cut emissions for factories and cities.",
    "logistics": "Our warehouses and trucks move goods across the country.",
    "retail": "We run an online store and a chain of shops.",
    "space": "We build small satellites and the ground stations that talk to them.",
    "gaming": "We make mobile and console games played by millions.",
    "semiconductor": "We design and test chips for phones and cars.",
    "infrastructure": "We build highways, ports and housing.",
}

FAMILY_SECTORS: dict[str, tuple[str, ...]] = {
    "embedded": ("healthcare", "semiconductor", "climate", "mobility"),
    "vlsi": ("semiconductor",),
    "robotics": ("retail", "logistics", "healthcare"),
    "mechanical": ("climate", "mobility", "infrastructure"),
    "thermal": ("space", "climate", "semiconductor"),
    "manufacturing": ("healthcare", "mobility", "climate"),
    "electrical": ("infrastructure", "climate", "space"),
    "civil": ("infrastructure", "climate"),
    "chemical": ("healthcare", "agriculture"),
    "finance": ("fintech", "retail"),
    "blockchain": ("fintech", "retail"),
    "vision": ("retail", "space", "agriculture", "healthcare"),
    "nlp": ("fintech", "education", "gaming"),
}
OFFICE_SECTORS = ("education", "retail", "mobility", "fintech", "space", "healthcare", "gaming")
CITIES = (
    "Kolkata",
    "Ahmedabad",
    "Jaipur",
    "Kochi",
    "Bengaluru",
    "Hyderabad",
    "Indore",
    "Mumbai",
    "Pune",
)

BLIND = Variant(
    seed=BLIND_SEED,
    per_family=4,
    prefix="blind:",
    text=TEXT,
    sectors=SECTORS,
    cities=CITIES,
    family_sectors=FAMILY_SECTORS,
    office_sectors=OFFICE_SECTORS,
)
