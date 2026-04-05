"""
coordinator.py – orchestrates the full ingestion pipeline.

For a given topic query:
  1. Fetch documents from all sources (PubMed, CDC, WHO, FDA)
  2. Compute trust scores for each document
  3. Upsert documents into the `documents` table
  4. Chunk each document's text
  5. Embed the chunks in batches
  6. Save chunks (with embeddings) to the `chunks` table

This runs on startup (seed) and on a cron schedule (updates).
"""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.sources.pubmed import PubMedFetcher
from app.ingestion.sources.cdc import CDCFetcher
from app.ingestion.sources.who import WHOFetcher
from app.ingestion.sources.fda import FDAFetcher
from app.ingestion.chunker import make_chunks_for_document
from app.ingestion.embedder import embed_batch
from app.services.trust_scorer import compute_trust_score
from app.services.metrics_service import documents_ingested_total

# Medical topics we seed the knowledge base with
DEFAULT_TOPICS = [

    # ── Cardiovascular ────────────────────────────────────────────────────────
    "hypertension treatment guidelines",
    "heart failure treatment guidelines",
    "atrial fibrillation management",
    "coronary artery disease treatment",
    "acute myocardial infarction management",
    "cardiovascular disease prevention",
    "anticoagulation therapy atrial fibrillation",
    "statin therapy cardiovascular",
    "ACE inhibitor heart failure",
    "cardiac arrhythmia treatment",
    "peripheral artery disease management",
    "deep vein thrombosis treatment",
    "pulmonary embolism management",
    "aortic stenosis treatment",
    "cardiomyopathy management",
    "pericarditis treatment",
    "endocarditis antibiotic treatment",
    "stroke prevention anticoagulation",
    "hypertensive crisis management",
    "cardiac rehabilitation outcomes",

    # ── Metabolic / Endocrine ─────────────────────────────────────────────────
    "diabetes mellitus management",
    "type 2 diabetes treatment",
    "type 1 diabetes insulin therapy",
    "insulin therapy diabetes",
    "metformin diabetes outcomes",
    "GLP-1 agonist diabetes treatment",
    "thyroid disease treatment",
    "hypothyroidism levothyroxine",
    "hyperthyroidism treatment",
    "Cushing syndrome management",
    "Addison disease treatment",
    "obesity treatment bariatric",
    "metabolic syndrome management",
    "dyslipidemia treatment guidelines",
    "hyperuricemia gout treatment",
    "polycystic ovary syndrome treatment",
    "adrenal insufficiency management",
    "growth hormone deficiency treatment",
    "hyperparathyroidism treatment",
    "diabetes insipidus management",

    # ── Respiratory ───────────────────────────────────────────────────────────
    "asthma treatment guidelines",
    "COPD treatment guidelines",
    "pneumonia treatment antibiotics",
    "COVID-19 clinical outcomes",
    "COVID-19 treatment antivirals",
    "influenza treatment oseltamivir",
    "tuberculosis treatment regimen",
    "pulmonary fibrosis treatment",
    "sarcoidosis management",
    "sleep apnea CPAP treatment",
    "bronchiectasis management",
    "pleural effusion management",
    "respiratory failure mechanical ventilation",
    "interstitial lung disease treatment",
    "cystic fibrosis treatment",
    "pneumothorax management",
    "lung transplantation outcomes",
    "allergic rhinitis treatment",
    "chronic cough management",
    "hypersensitivity pneumonitis treatment",

    # ── Gastroenterology ──────────────────────────────────────────────────────
    "inflammatory bowel disease treatment",
    "Crohn disease management",
    "ulcerative colitis treatment",
    "irritable bowel syndrome management",
    "gastroesophageal reflux disease treatment",
    "peptic ulcer disease treatment",
    "celiac disease management",
    "liver cirrhosis management",
    "hepatitis B treatment antivirals",
    "hepatitis C treatment direct acting antivirals",
    "non-alcoholic fatty liver disease treatment",
    "pancreatitis management",
    "cholecystitis gallstone treatment",
    "colorectal polyp screening",
    "gastrointestinal bleeding management",
    "Helicobacter pylori eradication",
    "diverticulitis treatment",
    "constipation chronic treatment",
    "acute liver failure management",
    "eosinophilic esophagitis treatment",

    # ── Neurology ─────────────────────────────────────────────────────────────
    "stroke treatment acute management",
    "stroke rehabilitation outcomes",
    "epilepsy antiepileptic treatment",
    "multiple sclerosis disease modifying therapy",
    "Parkinson disease treatment",
    "Alzheimer disease treatment",
    "dementia management",
    "migraine treatment prevention",
    "headache cluster treatment",
    "neuropathic pain management",
    "Guillain-Barre syndrome treatment",
    "myasthenia gravis treatment",
    "amyotrophic lateral sclerosis management",
    "meningitis antibiotic treatment",
    "encephalitis management",
    "traumatic brain injury management",
    "spinal cord injury rehabilitation",
    "peripheral neuropathy treatment",
    "restless leg syndrome treatment",
    "Huntington disease management",

    # ── Psychiatry / Mental Health ────────────────────────────────────────────
    "mental health depression treatment",
    "antidepressant therapy outcomes",
    "anxiety disorder treatment",
    "bipolar disorder treatment",
    "schizophrenia antipsychotic treatment",
    "ADHD treatment methylphenidate",
    "PTSD treatment therapy",
    "obsessive compulsive disorder treatment",
    "eating disorder anorexia treatment",
    "substance use disorder opioid treatment",
    "alcohol use disorder treatment",
    "cognitive behavioral therapy outcomes",
    "suicide prevention intervention",
    "insomnia treatment CBT",
    "autism spectrum disorder management",
    "borderline personality disorder treatment",
    "panic disorder treatment",
    "psychosis first episode treatment",
    "electroconvulsive therapy outcomes",
    "mindfulness mental health outcomes",

    # ── Infectious Disease ────────────────────────────────────────────────────
    "antibiotic resistance management",
    "sepsis management guidelines",
    "HIV antiretroviral therapy",
    "malaria treatment antimalarials",
    "dengue fever management",
    "Lyme disease antibiotic treatment",
    "urinary tract infection treatment",
    "skin soft tissue infection treatment",
    "MRSA treatment vancomycin",
    "Clostridioides difficile treatment",
    "fungal infection antifungal treatment",
    "vaccine safety efficacy",
    "COVID-19 vaccination outcomes",
    "influenza vaccination effectiveness",
    "pneumococcal vaccine outcomes",
    "herpes zoster treatment acyclovir",
    "sexually transmitted infection treatment",
    "tropical disease leishmaniasis treatment",
    "rabies post-exposure prophylaxis",
    "Ebola virus disease management",

    # ── Oncology — General ────────────────────────────────────────────────────
    "cancer screening recommendations",
    "cancer immunotherapy checkpoint inhibitors",
    "chemotherapy side effects management",
    "radiation therapy cancer outcomes",
    "palliative care cancer pain",
    "cancer biomarker targeted therapy",
    "cancer surgery outcomes",
    "cancer survivorship quality of life",
    "cancer cachexia management",
    "oncology clinical trial outcomes",

    # ── Oncology — Specific Cancers ───────────────────────────────────────────
    "lung cancer treatment immunotherapy",
    "breast cancer treatment hormonal therapy",
    "colorectal cancer chemotherapy",
    "prostate cancer treatment",
    "pancreatic cancer management",
    "leukemia treatment chemotherapy",
    "lymphoma treatment rituximab",
    "melanoma immunotherapy treatment",
    "ovarian cancer chemotherapy",
    "cervical cancer treatment",
    "liver hepatocellular carcinoma treatment",
    "bladder cancer treatment",
    "kidney renal cell carcinoma treatment",
    "thyroid cancer management",
    "brain glioblastoma treatment",
    "stomach gastric cancer treatment",
    "esophageal cancer treatment",
    "head neck cancer treatment",
    "multiple myeloma treatment",
    "sarcoma treatment outcomes",
    "testicular cancer chemotherapy",
    "endometrial uterine cancer treatment",
    "mesothelioma treatment",
    "neuroblastoma pediatric treatment",
    "Hodgkin lymphoma treatment",
    "non-Hodgkin lymphoma treatment",
    "acute myeloid leukemia treatment",
    "chronic lymphocytic leukemia treatment",
    "medulloblastoma treatment",
    "carcinoid neuroendocrine tumor treatment",

    # ── DNA / Genomics / Precision Medicine ───────────────────────────────────
    "CRISPR gene editing clinical applications",
    "gene therapy clinical trials outcomes",
    "pharmacogenomics drug response",
    "whole genome sequencing clinical diagnosis",
    "next generation sequencing cancer",
    "DNA mismatch repair cancer",
    "BRCA1 BRCA2 mutation cancer risk",
    "liquid biopsy circulating tumor DNA",
    "epigenetics cancer treatment",
    "DNA methylation cancer biomarker",
    "RNA sequencing transcriptomics disease",
    "single cell sequencing clinical applications",
    "copy number variation disease",
    "somatic mutation cancer driver genes",
    "germline mutation hereditary cancer",
    "tumor mutational burden immunotherapy",
    "microsatellite instability cancer treatment",
    "HER2 amplification breast cancer treatment",
    "KRAS mutation lung cancer treatment",
    "EGFR mutation targeted therapy",
    "ALK rearrangement lung cancer",
    "PD-L1 expression immunotherapy",
    "CAR-T cell therapy cancer",
    "stem cell transplantation outcomes",
    "bone marrow transplantation outcomes",
    "clonal hematopoiesis aging cancer",
    "mitochondrial DNA disease",
    "telomere length aging disease",
    "DNA repair mechanisms cancer",
    "hereditary genetic disease management",
    "down syndrome trisomy 21 management",
    "cystic fibrosis CFTR mutation treatment",
    "sickle cell disease gene therapy",
    "thalassemia gene therapy treatment",
    "Huntington disease genetic counseling",
    "fragile X syndrome management",
    "Turner syndrome treatment",
    "Marfan syndrome management",
    "neurofibromatosis treatment",
    "genomic medicine implementation",

    # ── Rheumatology ─────────────────────────────────────────────────────────
    "rheumatoid arthritis biologic treatment",
    "systemic lupus erythematosus treatment",
    "ankylosing spondylitis treatment",
    "psoriatic arthritis treatment",
    "osteoarthritis treatment",
    "gout treatment allopurinol",
    "vasculitis treatment",
    "Sjogren syndrome management",
    "fibromyalgia treatment",
    "polymyalgia rheumatica treatment",

    # ── Nephrology ────────────────────────────────────────────────────────────
    "chronic kidney disease management",
    "acute kidney injury management",
    "dialysis hemodialysis outcomes",
    "kidney transplantation outcomes",
    "nephrotic syndrome treatment",
    "IgA nephropathy treatment",
    "polycystic kidney disease management",
    "kidney stone urolithiasis treatment",
    "hypertension kidney disease",
    "contrast nephropathy prevention",

    # ── Hematology ────────────────────────────────────────────────────────────
    "anemia iron deficiency treatment",
    "anemia chronic disease management",
    "thrombocytopenia treatment",
    "hemophilia treatment factor replacement",
    "sickle cell disease management",
    "thalassemia management",
    "myelodysplastic syndrome treatment",
    "coagulation disorder management",
    "platelet disorder treatment",
    "erythropoietin anemia treatment",

    # ── Dermatology ───────────────────────────────────────────────────────────
    "psoriasis biologic treatment",
    "atopic dermatitis eczema treatment",
    "acne vulgaris treatment",
    "melanoma skin cancer treatment",
    "urticaria treatment antihistamine",
    "rosacea treatment",
    "contact dermatitis management",
    "wound healing chronic ulcer treatment",
    "alopecia treatment",
    "vitiligo treatment",

    # ── Orthopedics / Musculoskeletal ─────────────────────────────────────────
    "osteoporosis treatment prevention",
    "fracture healing management",
    "knee osteoarthritis treatment",
    "hip replacement outcomes",
    "back pain chronic management",
    "rotator cuff injury treatment",
    "sports injury rehabilitation",
    "bone metastasis treatment",
    "spinal stenosis treatment",
    "tendinopathy treatment",

    # ── Pediatrics ────────────────────────────────────────────────────────────
    "pediatric fever management",
    "pediatric asthma treatment",
    "pediatric vaccination schedule",
    "neonatal sepsis treatment",
    "pediatric epilepsy treatment",
    "childhood obesity management",
    "pediatric diabetes management",
    "kawasaki disease treatment",
    "RSV respiratory syncytial virus treatment",
    "pediatric cancer leukemia treatment",

    # ── Obstetrics / Gynecology ───────────────────────────────────────────────
    "pregnancy hypertension preeclampsia",
    "gestational diabetes management",
    "preterm labor prevention treatment",
    "postpartum depression treatment",
    "endometriosis treatment",
    "menopause hormone therapy",
    "infertility IVF outcomes",
    "cervical cancer HPV screening",
    "ovarian cyst management",
    "maternal mortality prevention",

    # ── Emergency Medicine ────────────────────────────────────────────────────
    "fever management treatment",
    "pain management analgesics",
    "sepsis emergency management",
    "trauma resuscitation management",
    "anaphylaxis treatment epinephrine",
    "overdose toxicology management",
    "cardiac arrest CPR outcomes",
    "emergency airway management",
    "burn injury management",
    "hypertensive emergency treatment",

    # ── Preventive Medicine ───────────────────────────────────────────────────
    "cancer screening colorectal",
    "mammography breast cancer screening",
    "cardiovascular risk prevention",
    "smoking cessation treatment",
    "physical activity health outcomes",
    "nutrition diet chronic disease",
    "alcohol reduction intervention",
    "STI prevention screening",
    "mental health prevention intervention",
    "occupational health disease prevention",
]


async def ingest_topic(db: AsyncSession, query: str, max_per_source: int = 30) -> int:
    """
    Fetch, process, and store documents for a single topic query.
    Returns the number of new documents stored.
    """
    results = await fetch_topic_documents(query, max_per_source=max_per_source)

    new_doc_count = 0

    for source_docs in results:
        if isinstance(source_docs, Exception):
            # Log but continue — one failing source shouldn't stop ingestion
            print(f"[ingestion] fetch error: {source_docs}")
            continue

        for doc_data in source_docs:
            stored = await _store_document(db, doc_data)
            if stored:
                new_doc_count += 1

    return new_doc_count


async def fetch_topic_documents(
    query: str,
    max_per_source: int = 30,
    source_names: list[str] | None = None,
) -> list[list[dict] | Exception]:
    """Fetch topic documents from the requested sources without storing them."""
    fetchers = _get_fetchers(source_names)
    fetch_tasks = [fetcher.fetch(query, max_per_source) for fetcher in fetchers]
    return await asyncio.gather(*fetch_tasks, return_exceptions=True)


async def ingest_all_topics(db: AsyncSession, max_per_source: int = 30) -> None:
    """Run ingestion for all default topics. Called by the scheduler."""
    total = 0
    for topic in DEFAULT_TOPICS:
        try:
            count = await ingest_topic(db, topic, max_per_source=max_per_source)
            total += count
            print(f"[ingestion] '{topic}' → {count} new documents")
        except Exception as e:
            print(f"[ingestion] error for topic '{topic}': {e}")
    print(f"[ingestion] complete. {total} total new documents ingested.")


def _get_fetchers(source_names: list[str] | None = None) -> list:
    source_map = {
        "pubmed": PubMedFetcher,
        "cdc": CDCFetcher,
        "who": WHOFetcher,
        "fda": FDAFetcher,
    }
    if not source_names:
        source_names = list(source_map)
    return [source_map[name.lower()]() for name in source_names if name.lower() in source_map]


async def _store_document(db: AsyncSession, doc_data: dict) -> bool:
    """
    Insert a document and its chunks into the database.
    Returns True if this was a new document (not a duplicate).
    """
    # Check for duplicates by source + source_id
    existing = await db.execute(
        text("SELECT id FROM documents WHERE source_id = :sid"),
        {"sid": doc_data["source_id"]},
    )
    row = existing.fetchone()
    if row:
        return False   # Already ingested

    # Compute trust score
    trust = compute_trust_score(
        source=doc_data["source"],
        publication_type=doc_data["publication_type"],
        published_at=doc_data.get("published_at"),
        citation_count=doc_data.get("citation_count", 0),
    )

    # Insert document
    result = await db.execute(
        text("""
            INSERT INTO documents
                (source, source_id, title, authors, journal, doi, url,
                 published_at, publication_type, trust_score, ingested_at)
            VALUES
                (:source, :source_id, :title, :authors, :journal, :doi, :url,
                 :published_at, :publication_type, :trust_score, :ingested_at)
            RETURNING id
        """),
        {
            "source": doc_data["source"],
            "source_id": doc_data["source_id"],
            "title": doc_data["title"],
            "authors": doc_data.get("authors", ""),
            "journal": doc_data.get("journal", ""),
            "doi": doc_data.get("doi", ""),
            "url": doc_data.get("url", ""),
            "published_at": doc_data.get("published_at"),
            "publication_type": doc_data.get("publication_type", "unknown"),
            "trust_score": trust,
            "ingested_at": datetime.now(timezone.utc),
        },
    )
    await db.commit()

    doc_id = result.fetchone()[0]

    # Chunk the document text
    chunks = make_chunks_for_document(
        document_id=doc_id,
        text=doc_data["text"],
        source=doc_data["source"],
        source_id=doc_data["source_id"],
        trust_score=trust,
    )

    if not chunks:
        return True

    # Embed all chunks in one batch (faster than one by one)
    texts = [c["content"] for c in chunks]
    embeddings = embed_batch(texts)

    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding

    # Save to database
    from app.services.vector_store import save_chunks
    await save_chunks(db, chunks)

    # Update Prometheus gauge
    documents_ingested_total.labels(source=doc_data["source"]).inc()

    return True
