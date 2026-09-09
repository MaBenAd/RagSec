from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import re
import textwrap
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import sys


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.services.groq_service import call_groq

FAQ_DIR = ROOT_DIR / "backend" / "data" / "faq"
DOCS_DIR = ROOT_DIR / "docs" / "rag"
BASE_URL = "https://ensabm.usms.ac.ma/"
DOMAIN = "ensabm.usms.ac.ma"
TARGET_COUNT = 7000

USER_AGENT = "Chatbot-USMS-PFA/1.0 (+educational ENSA BM RAG refresh)"

PRIORITY_HTML_URLS = [
    "https://ensabm.usms.ac.ma/",
    "https://ensabm.usms.ac.ma/mot-du-directeur/",
    "https://ensabm.usms.ac.ma/2021/12/avis-demande-de-documents/",
    "https://ensabm.usms.ac.ma/lancement-de-lespace-etudiant-ensa-beni-mellal/",
    "https://ensabm.usms.ac.ma/edt/index.php",
    "https://ensabm.usms.ac.ma/orientation-et-choix-de-la-filiere-ingenieur/",
    "https://ensabm.usms.ac.ma/2022/01/consignes-pour-les-examens/",
    "https://ensabm.usms.ac.ma/api/",
    "https://ensabm.usms.ac.ma/g2er/",
    "https://ensabm.usms.ac.ma/iaa/",
    "https://ensabm.usms.ac.ma/iacs/",
    "https://ensabm.usms.ac.ma/tdi/",
    "https://ensabm.usms.ac.ma/partenariats-ensabm/",
]

PRIORITY_PDF_URLS = [
    "https://ensabm.usms.ac.ma/iacs/Docs/ENSABM_Brochure_intelligence_artificielle_et_cybersecurite.pdf",
    "https://ensabm.usms.ac.ma/apps2024/docs/IAC.pdf",
]


@dataclass
class PageDoc:
    url: str
    title: str
    description: str = ""
    headings: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    lists: list[str] = field(default_factory=list)
    raw_text: str = ""


TRACK_FACTS = {
    "2AP": {
        "name": "Deux Annees Preparatoires au Cycle Ingenieur",
        "short_name": "2AP",
        "url": "https://ensabm.usms.ac.ma/api/",
        "coordinator": "M. Mohamed KAAB",
        "coordinator_variants": ["Mohamed KAAB", "KAAB MOHAMED", "Pr. KAAB MOHAMED"],
        "email": "m.kaab@usms.ma",
        "summary": (
            "Les 2AP constituent les deux annees preparatoires integrees de l'ENSA Beni Mellal. "
            "Elles preparent les etudiants aux filieres du cycle ingenieur : G2ER, IAA, IACS et TDI."
        ),
        "admission": (
            "L'acces aux 2AP se fait via le concours national d'acces aux ENSA/ENSAM, puis selon le dossier "
            "et le classement des candidats."
        ),
        "keywords": "mathematiques, physique, chimie, informatique, communication, sciences de l'ingenieur",
        "duration": "2 ans",
        "credits": "120 credits",
        "semesters": "4 semestres",
        "language": "francais, arabe et anglais",
        "mode": "presentiel",
        "program": (
            "Le programme couvre analyse mathematique, algebre, physique, chimie, probabilites et statistiques, "
            "circuits electriques, electronique analogique, mecanique du solide, automatique lineaire, culture "
            "digitale, programmation en langage C, modelisation et simulation, methodologie scientifique, "
            "francais scientifique et anglais technique."
        ),
        "skills": (
            "Les 2AP developpent les bases scientifiques, la rigueur de raisonnement, les competences numeriques, "
            "la programmation, la communication scientifique et la preparation au cycle ingenieur."
        ),
        "jobs": (
            "Les 2AP ne sont pas une filiere de sortie professionnelle directe : elles preparent l'acces au cycle "
            "ingenieur et au diplome d'ingenieur d'Etat."
        ),
        "sectors": "orientation vers G2ER, IAA, IACS ou TDI selon le classement, le projet et les places disponibles",
        "stages": "La page officielle 2AP presente surtout la formation preparatoire; les stages concernent ensuite le cycle ingenieur.",
        "infrastructure": "amphitheatre, salles de cours/TD, salles de TP, salle informatique et salle d'enseignement a distance prevue",
        "partners": "Polytech Angers, EILCO/ULCO, EPT, CRI, AUF, SUTA, Agence du Bassin Hydraulique Oum Rabia, CGEM",
    },
    "G2ER": {
        "name": "Genie Electrique et Energies Renouvelables",
        "short_name": "G2ER",
        "url": "https://ensabm.usms.ac.ma/g2er/",
        "coordinator": "M. Mostapha OULCAID",
        "coordinator_variants": ["Mostapha OULCAID", "OULCAID MOSTAPHA", "M. MOSTAPHA OULCAID"],
        "email": "m.oulcaid@usms.ma",
        "summary": (
            "La filiere G2ER forme des ingenieurs capables de concevoir, optimiser et gerer des systemes "
            "electriques et des installations d'energies renouvelables."
        ),
        "admission": (
            "L'integration se fait apres le cycle preparatoire ou par admission parallele selon les conditions "
            "de selection de l'ENSA Beni Mellal."
        ),
        "keywords": "reseaux electriques, energies solaire et eolienne, electronique de puissance, smart grid",
        "duration": "3 ans de cycle ingenieur",
        "credits": "150 credits",
        "semesters": "6 semestres",
        "language": "francais",
        "mode": "presentiel avec mobilite nationale et internationale",
        "program": (
            "Le parcours G2ER couvre les fondamentaux electriques, les systemes industriels et le traitement du signal, "
            "l'automatisation, l'electronique de puissance, les energies renouvelables, les systemes de conversion, "
            "les reseaux, le stockage et le management de l'energie. Le semestre 6 est consacre au PFE."
        ),
        "skills": (
            "La filiere developpe les competences en conception de systemes electriques, automatisation, energies "
            "renouvelables, reseaux intelligents, efficacite energetique, simulation, gestion de projet et travail en equipe."
        ),
        "jobs": (
            "Les debouches incluent ingenieur en energies renouvelables, ingenieur electricien, ingenieur reseaux "
            "electriques, automaticien, charge d'affaires energie, chef de projet energie et ingenieur bureau d'etudes."
        ),
        "sectors": (
            "ONEE, MASEN, IRESEN, industries automobile/transport/aeronautique, centrales solaires et eoliennes, "
            "bureaux d'etudes et d'expertise electrique et energetique."
        ),
        "stages": "Le semestre 6 correspond au Projet de Fin d'Etudes en entreprise ou laboratoire, avec memoire et soutenance.",
        "infrastructure": (
            "plateformes de TP photovoltaique, pompage solaire, automatique, instrumentation industrielle, regulation, "
            "automatismes et robotique, electronique de puissance, geothermie, solaire thermique et smart grid."
        ),
        "partners": "Polytech Angers, EILCO, Universite Savoie Mont Blanc, ULCO, Universite de Bretagne Occidentale, EPT, CRI, AUF, CGEM, SUTA",
    },
    "IAA": {
        "name": "Industries AgroAlimentaires",
        "short_name": "IAA",
        "url": "https://ensabm.usms.ac.ma/iaa/",
        "coordinator": "M. Yahya ROKNI",
        "coordinator_variants": ["Yahya ROKNI", "ROKNI YAHYA", "M. YAHYA ROKNI"],
        "email": "agroalimentaire.ensa@gmail.com",
        "summary": (
            "La filiere IAA forme des ingenieurs polyvalents capables d'intervenir dans la chaine "
            "agroalimentaire, la qualite, la transformation, la securite alimentaire et l'innovation."
        ),
        "admission": (
            "La filiere est accessible apres classes preparatoires ou via une formation universitaire Bac+2 "
            "dans des domaines compatibles, avec etude du dossier, epreuve ecrite et entretien oral."
        ),
        "keywords": "agroalimentaire, qualite, microbiologie, biochimie, biotechnologie alimentaire",
        "duration": "3 ans de cycle ingenieur",
        "credits": "150 credits",
        "semesters": "6 semestres",
        "language": "francais, arabe et anglais",
        "mode": "formation hybride indiquee sur la page, majoritairement en presentiel",
        "program": (
            "Le parcours IAA couvre bases scientifiques, biochimie alimentaire, procedes, qualite, hygiene, HACCP, "
            "technologies de transformation et conservation, toxicologie alimentaire, informatique industrielle, "
            "innovation et Projet de Fin d'Etudes."
        ),
        "skills": (
            "La filiere developpe les competences en qualite, microbiologie alimentaire, biochimie, biotechnologie, "
            "genie des procedes, management de la qualite, securite alimentaire, innovation et communication trilingue."
        ),
        "jobs": (
            "Les debouches incluent ingenieur qualite, ingenieur procedes et production, responsable management qualite, "
            "ingenieur R&D, consultant agroalimentaire, fonctions en laboratoire, audit et certification."
        ),
        "sectors": (
            "entreprises de transformation alimentaire, cooperatives agroalimentaires, import/export alimentaire, ONSSA, "
            "Morocco-Foodex, laboratoires d'analyse, bureaux de conseil, organismes de certification, pharmaceutique et nutraceutique."
        ),
        "stages": "Le semestre 6 correspond au Projet de Fin d'Etudes en entreprise ou laboratoire, avec memoire et soutenance.",
        "infrastructure": (
            "amphitheatre, salles de cours/TD, salles de TP, salle informatique, bibliotheque, ateliers industriels, "
            "fermenteurs, spectrophotometre UV/Visible, autoclave, HPLC/CPG, PCR, secheur et cabines d'analyse sensorielle."
        ),
        "partners": "Universite Savoie Mont Blanc, EILCO, Polytech Angers, EPT, UBO/ESIAB, ULCO, AUF, SUTA/COSUMAR, CRI, CGEM",
    },
    "IACS": {
        "name": "Intelligence Artificielle et Cybersecurite",
        "short_name": "IACS",
        "url": "https://ensabm.usms.ac.ma/iacs/",
        "source_url": "https://ensabm.usms.ac.ma/iacs/Docs/ENSABM_Brochure_intelligence_artificielle_et_cybersecurite.pdf",
        "coordinator": "Pr. Mohamed GOUSKIR",
        "coordinator_variants": ["Mohamed GOUSKIR", "GOUSKIR MOHAMED", "Pr. MOHAMED GOUSKIR"],
        "email": "m.gouskir@usms.ma",
        "summary": (
            "La filiere IACS forme des ingenieurs capables de concevoir des systemes intelligents, "
            "d'exploiter l'IA et la data science, et de securiser les infrastructures numeriques."
        ),
        "admission": (
            "L'acces a IACS est possible apres cycle preparatoire ENSA ou equivalent, classes preparatoires "
            "scientifiques, ou formation Bac+2 compatible selon les conditions d'admission."
        ),
        "keywords": "IA, machine learning, deep learning, data science, cybersecurite, pentesting, cloud, DevSecOps",
        "duration": "3 ans de cycle ingenieur apres 2 ans preparatoires, soit un parcours Bac+5",
        "credits": "180 credits ECTS pour le diplome indique sur la page",
        "semesters": "6 semestres du cycle ingenieur",
        "language": "enseignement en francais",
        "mode": "presentiel",
        "program": (
            "Le programme IACS combine 57% IA/Data Science et 43% Cybersecurite. Il couvre programmation Python, "
            "bases de donnees PL/SQL, reseaux, mathematiques pour l'IA, architectures logicielles, cloud, machine learning, "
            "big data, cryptographie, NLP, deep learning, cyberdefense, IAM, IoT security, forensics, DevSecOps, "
            "gouvernance, IA generative et PFE."
        ),
        "skills": (
            "La filiere developpe les competences en conception de modeles IA, analyse de donnees massives, audit et "
            "securisation des systemes, detection des cybermenaces, cloud securise, IA appliquee a la cybersecurite et gestion de projet."
        ),
        "jobs": (
            "Les debouches incluent ingenieur machine learning/deep learning, data scientist, data engineer, ingenieur "
            "cybersecurite, analyste SOC, pentester, architecte cloud, consultant IA/securite, ingenieur forensics et RSSI."
        ),
        "sectors": "banques, assurances, fintech, cybersecurite, defense, ESN, telecoms, sante, e-gouvernement, industrie 4.0, IoT, R&D",
        "stages": (
            "IACS comporte trois stages : stage de decouverte de 4 semaines apres S2, stage d'assistant ingenieur de "
            "8 semaines apres S4, puis PFE de 4 a 6 mois en S6."
        ),
        "infrastructure": "formation numerique orientee IA, data, reseaux, cybersecurite, cloud, DevSecOps et projets pratiques",
        "partners": "Polytech Annecy-Chambery, Polytech Angers, EIL Cote d'Opale, ENSICAEN, CRI, COSUMAR, Agence du Bassin Hydraulique, CGEM, Commune de Beni Mellal",
        "student_life": "Le club CSIA est associe a la filiere IACS et anime des ateliers, CTF, hackathons, challenges et projets open source.",
    },
    "TDI": {
        "name": "Transformation Digitale Industrielle",
        "short_name": "TDI",
        "url": "https://ensabm.usms.ac.ma/tdi/",
        "coordinator": "M. Hamid OUANAN",
        "coordinator_variants": ["Hamid OUANAN", "OUANAN HAMID", "M. HAMID OUANAN"],
        "email": "ham.ouanan@gmail.com",
        "summary": (
            "La filiere TDI forme des ingenieurs capables de piloter la transformation numerique des entreprises "
            "industrielles, a la croisee du genie industriel, de l'informatique et de l'industrie 4.0."
        ),
        "admission": (
            "La filiere est accessible apres le cycle preparatoire ou par admission parallele selon le dossier, "
            "les acquis scientifiques et l'entretien."
        ),
        "keywords": "industrie 4.0, transformation digitale, IIoT, automatisation, cloud industriel, data, IA industrielle",
        "duration": "3 ans de cycle ingenieur",
        "credits": "150 credits",
        "semesters": "6 semestres",
        "language": "francais",
        "mode": "presentiel avec mobilite internationale",
        "program": (
            "Le parcours TDI couvre les fondamentaux industriels, cloud et bases de donnees, automatisation, IIoT, "
            "programmation, smart factory, robotique, cybersecurite industrielle, data analytics, IA appliquee a l'industrie "
            "et Projet de Fin d'Etudes."
        ),
        "skills": (
            "La filiere developpe les competences en automatisation, supervision industrielle, cloud industriel, data analytics, "
            "big data, IA industrielle, bases de donnees Industrie 4.0, cybersecurite industrielle, ERP/MES et gestion de projet."
        ),
        "jobs": (
            "Les debouches incluent ingenieur transformation digitale, ingenieur automatisation/supervision, data scientist "
            "industriel, ingenieur cloud industriel, ingenieur IIoT, consultant Industrie 4.0 et chef de projet digital industriel."
        ),
        "sectors": (
            "industrie manufacturiere, automobile, aeronautique, ferroviaire, PME et multinationales en transformation digitale, "
            "agro-industrie, textile, metallurgie, chimie, SCADA, ERP/MES et cabinets de conseil."
        ),
        "stages": (
            "La page TDI indique des stages obligatoires apres S2 et S4, puis un PFE au semestre 6 avec memoire et soutenance."
        ),
        "infrastructure": (
            "station de calcul, salles TP, salle reseau/supervision industrielle, laboratoire IA industrielle, casques AR/VR, "
            "studio MOOC, tableaux interactifs, serveur cloud industriel prive et licences Microsoft."
        ),
        "partners": "Polytech Angers, EILCO/ULCO, Universite Savoie Mont Blanc, EPT, CRI, AUF, SUTA/COSUMAR, Agence du Bassin Hydraulique, CGEM",
    },
}


TRACK_ALIASES = {
    "2AP": ["2ap", "api", "cycle preparatoire", "classes preparatoires", "deux annees preparatoires"],
    "G2ER": [
        "g2er",
        "geer",
        "genie electrique",
        "energies renouvelables",
        "genie electrique et energies renouvelables",
        "genie electrique energies renouvelables",
    ],
    "IAA": [
        "iaa",
        "industries agroalimentaires",
        "industrie agroalimentaire",
        "industries agro alimentaires",
        "industrie agro alimentaire",
        "agroalimentaire",
    ],
    "IACS": [
        "iacs",
        "iac",
        "intelligence artificielle",
        "intellignece artificielle",
        "intelligence artificielle et cybersecurite",
        "intellignece artificielle et cybersecurite",
        "cybersecurite",
        "cyber securite",
        "ia et cybersecurite",
        "ia cybersecurite",
    ],
    "TDI": [
        "tdi",
        "transformation digitale industrielle",
        "transformation digitale",
        "transformation numerique industrielle",
        "digitalisation industrielle",
        "industrie 4.0",
    ],
}

TRACK_SEMESTER_PROGRAMS = {
    "G2ER": {
        "S1": {
            "title": "Fondamentaux Scientifiques et Electriques",
            "modules": [
                "Mathematiques pour l'Ingenieur",
                "Electronique Analogique",
                "Electronique Numerique et Introduction aux Circuits Programmables",
                "Electrotechnique Generale",
                "Thermodynamique des Installations Industrielles",
                "Francais Technique",
                "RSE et Developpement Durable",
            ],
            "source_url": "https://ensabm.usms.ac.ma/g2er/",
        },
        "S2": {
            "title": "Systemes Industriels et Traitement de Signal",
            "modules": [
                "Capteurs et Instrumentation Industrielle",
                "Traitement de Signal",
                "Informatique Industrielle",
                "Machines Electriques",
                "Foundations of Technical and Scientific English",
                "Python Avance",
                "Transfert Thermique Applique",
            ],
            "note": "Stage en entreprise obligatoire en fin de semestre 2.",
            "source_url": "https://ensabm.usms.ac.ma/g2er/",
        },
        "S3": {
            "title": "Automatisation, Puissance et Electronique",
            "modules": [
                "Equipements et Installations Electriques",
                "Electronique de Puissance",
                "Automatique Lineaire et Non Lineaire",
                "Automatismes Industriels",
                "Francais Professionnel",
                "Droit et Redaction Administrative",
                "Analyse Numerique",
            ],
            "source_url": "https://ensabm.usms.ac.ma/g2er/",
        },
        "S4": {
            "title": "Energies Renouvelables et Systemes de Conversion",
            "modules": [
                "Commandes des Machines Electriques",
                "Mecanique des Fluides",
                "Chaine de Conversion Eolienne",
                "Systemes Solaires PV et CSP",
                "Communicating in Scientific Contexts",
                "Intelligence Artificielle et Applications",
                "Apprentissage par Projet",
            ],
            "note": "Stage en entreprise obligatoire en fin de semestre 4.",
            "source_url": "https://ensabm.usms.ac.ma/g2er/",
        },
        "S5": {
            "title": "Reseaux, Stockage et Management de l'Energie",
            "modules": [
                "Qualite de l'Energie et Injection au Reseau",
                "Stockage de l'Energie et Cogeneration",
                "Reseaux Electriques",
                "Management de l'Energie ISO 50001 et Bilan Carbone",
                "Schemas Electriques pour l'Industrie : Normes et Pratiques",
                "Scientific Writing and Professional Communication",
                "Gestion des Projets Energetiques",
            ],
            "source_url": "https://ensabm.usms.ac.ma/g2er/",
        },
        "S6": {
            "title": "Projet de Fin d'Etudes",
            "modules": ["Projet de Fin d'Etudes en entreprise ou laboratoire"],
            "source_url": "https://ensabm.usms.ac.ma/g2er/",
        },
    },
    "IAA": {
        "S1": {
            "title": "Bases Scientifiques et Techniques",
            "modules": [
                "Biochimie Structurale et Metabolique",
                "Biologie Cellulaire et Moleculaire",
                "Chimie Organique",
                "Mathematiques pour l'Ingenieur",
                "Thermodynamique Industrielle",
                "Francais Technique",
                "Programmation et Bioinformatique",
            ],
            "source_url": "https://ensabm.usms.ac.ma/iaa/",
        },
        "S2": {
            "title": "Biochimie Alimentaire et Procedes",
            "modules": [
                "Biochimie des Aliments",
                "Transferts Thermiques Appliques",
                "Production Animale et Vegetale",
                "Foundations of Technical and Scientific English",
                "Genie Enzymatique",
                "Droit et Redaction Administrative",
                "Analyse Numerique",
            ],
            "note": "Stage d'observation obligatoire de 20 jours en entreprise.",
            "source_url": "https://ensabm.usms.ac.ma/iaa/",
        },
        "S3": {
            "title": "Qualite, Hygiene et Management",
            "modules": [
                "Microbiologie Alimentaire et Biotechnologies Industrielles",
                "Bonnes Pratiques d'Hygiene et HACCP",
                "Management Qualite et Outils Qualite",
                "Intelligence Artificielle et Instrumentation",
                "Gestion de Production et MSP",
                "Francais Professionnel",
                "Chimiometrie et Plans d'Experiences",
            ],
            "source_url": "https://ensabm.usms.ac.ma/iaa/",
        },
        "S4": {
            "title": "Technologies de Transformation Alimentaire",
            "modules": [
                "Genie des Procedes Alimentaires",
                "Technologies de Transformation et Conservation I",
                "Technologies de Transformation et Conservation II",
                "Communicating in Scientific Contexts",
                "Maintenance Industrielle et Ordonnancement",
                "Alimentation et Nutrition Humaine",
                "Methodologies Innovantes d'Analyses",
            ],
            "note": "Stage technique obligatoire de 20 jours en entreprise.",
            "source_url": "https://ensabm.usms.ac.ma/iaa/",
        },
        "S5": {
            "title": "Specialisation et Innovation",
            "modules": [
                "Toxicologie Alimentaire",
                "Informatique Industrielle et Robotisation",
                "Referentiels Qualite ISO, BRC, IFS et FSSC",
                "Environnement et Developpement Durable",
                "Scientific Writing and Professional Communication",
                "Rheologie et Analyses Sensorielles",
                "Formulation et Conditionnement",
            ],
            "source_url": "https://ensabm.usms.ac.ma/iaa/",
        },
        "S6": {
            "title": "Projet de Fin d'Etudes",
            "modules": ["Projet de Fin d'Etudes en entreprise ou laboratoire"],
            "source_url": "https://ensabm.usms.ac.ma/iaa/",
        },
    },
    "IACS": {
        "S1": {
            "title": "Bases IA, data et programmation",
            "modules": [
                "Bases de Donnees PL/SQL",
                "Reseaux Informatiques",
                "Analyse Statistique et Data Science",
                "Mathematiques pour l'IA",
                "Programmation Python",
                "Francais Technique",
                "Methodologie et Soft Skills",
            ],
            "source_url": "https://ensabm.usms.ac.ma/iacs/Docs/ENSABM_Brochure_intelligence_artificielle_et_cybersecurite.pdf",
        },
        "S2": {
            "title": "Cloud, cryptographie et machine learning",
            "modules": [
                "Cloud Computing et Virtualisation",
                "Cryptographie",
                "Big Data et NoSQL",
                "Machine Learning",
                "Architectures Logiciels",
                "Gestion de Projet Agile",
                "Anglais Technique",
                "Stage 1",
            ],
            "source_url": "https://ensabm.usms.ac.ma/iacs/Docs/ENSABM_Brochure_intelligence_artificielle_et_cybersecurite.pdf",
        },
        "S3": {
            "title": "Deep learning, cyberdefense et identites",
            "modules": [
                "NLP et Text Mining",
                "Deep Learning",
                "Cybersecurite et Cyberdefense",
                "Gestion des Identites et Acces",
                "IoT et Edge Computing Security",
                "Francais Professionnel",
                "Innovation et Entrepreneuriat",
            ],
            "source_url": "https://ensabm.usms.ac.ma/iacs/Docs/ENSABM_Brochure_intelligence_artificielle_et_cybersecurite.pdf",
        },
        "S4": {
            "title": "Ethique, forensics, quantum et DevSecOps",
            "modules": [
                "Ethique et Droit Numerique",
                "Administration Securisee et Forensics",
                "Technologies Emergentes et Quantum Computing",
                "DevOps / DevSecOps",
                "Droit et Redaction Administrative",
                "Apprentissage par Projet",
                "Scientific and Professional Communication",
                "Stage 2",
            ],
            "source_url": "https://ensabm.usms.ac.ma/iacs/Docs/ENSABM_Brochure_intelligence_artificielle_et_cybersecurite.pdf",
        },
        "S5": {
            "title": "IA avancee, gouvernance, blockchain et big data",
            "modules": [
                "Compliance et Gouvernance International",
                "IA Avancee en Cybersecurite",
                "Blockchain",
                "Technologies Big Data Analytics",
                "IA Generative et IA Agentique",
                "Scientific and Professional Writing",
                "Recherche et Innovation",
            ],
            "source_url": "https://ensabm.usms.ac.ma/iacs/Docs/ENSABM_Brochure_intelligence_artificielle_et_cybersecurite.pdf",
        },
        "S6": {
            "title": "Projet de Fin d'Etudes",
            "modules": ["Projet de Fin d'Etudes"],
            "source_url": "https://ensabm.usms.ac.ma/iacs/Docs/ENSABM_Brochure_intelligence_artificielle_et_cybersecurite.pdf",
        },
    },
    "TDI": {
        "S1": {
            "title": "Fondamentaux Industriels et Numeriques",
            "modules": [
                "Recherche Operationnelle",
                "Bases de l'Electricite Industrielle",
                "Reseaux Informatiques",
                "Electronique Analogique et Numerique",
                "Mathematiques pour l'Ingenieur",
                "Francais Technique",
                "Digital Skills : Excel Avance et Python",
            ],
            "source_url": "https://ensabm.usms.ac.ma/tdi/",
        },
        "S2": {
            "title": "Systemes Industriels, Cloud et Bases de Donnees",
            "modules": [
                "Informatique Industrielle",
                "Cloud Computing et Virtualisation",
                "Analyse Numerique",
                "Foundations of Technical and Scientific English",
                "Outils Numeriques : MATLAB et Linux",
                "Ingenierie des Bases de Donnees",
                "Maintenance et Fiabilite Industrielle",
            ],
            "note": "Stage obligatoire en fin de semestre 2.",
            "source_url": "https://ensabm.usms.ac.ma/tdi/",
        },
        "S3": {
            "title": "Automatisation, IIoT et Programmation",
            "modules": [
                "Automatisation et Supervision Industrielle",
                "Employment Skills",
                "Machines Electriques",
                "Realite Virtuelle et Realite Augmentee pour l'Industrie 4.0",
                "Francais Professionnel",
                "Programmation Orientee Objet Avancee",
                "Internet Industriel des Objets IIoT",
            ],
            "source_url": "https://ensabm.usms.ac.ma/tdi/",
        },
        "S4": {
            "title": "IA Industrielle, Data Analytics et Gestion",
            "modules": [
                "Communicating in Scientific Contexts",
                "Apprentissage par Projet APP",
                "Logistique et Transport",
                "Analytique des Donnees Massives pour l'Industrie 4.0",
                "Intelligence Artificielle Appliquee a l'Industrie 4.0",
                "Gestion de Production, Lean Management et Controle Qualite",
                "Genie Logiciel",
            ],
            "note": "Stage obligatoire en fin de semestre 4.",
            "source_url": "https://ensabm.usms.ac.ma/tdi/",
        },
        "S5": {
            "title": "Smart Factory, Robotique et Cybersecurite",
            "modules": [
                "Gestion de Projet et Ordonnancement",
                "Optimisation Pilotee par les Donnees",
                "Normes et Schemas Industriels",
                "Cobotique et Robotique Industrielle",
                "Scientific Writing and Professional Communication",
                "Cybersecurite Industrielle",
                "Smart Factory",
            ],
            "source_url": "https://ensabm.usms.ac.ma/tdi/",
        },
        "S6": {
            "title": "Projet de Fin d'Etudes",
            "modules": ["Projet de Fin d'Etudes en entreprise ou laboratoire"],
            "source_url": "https://ensabm.usms.ac.ma/tdi/",
        },
    },
}


ADMIN_FAQS = [
    {
        "questions": [
            "Comment demander une attestation de scolarite",
            "Comment demander un releve de notes",
            "Ou demander les documents administratifs",
            "Comment recuperer une attestation administrative",
            "Je veux une attestation de scolarite que faire",
        ],
        "answer": (
            "Selon l'avis officiel de l'ENSA Beni Mellal, les demandes de documents administratifs "
            "(attestation de scolarite, releve de notes, etc.) se font via l'Espace Numerique de Travail ENT."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/2021/12/avis-demande-de-documents/",
        "source_title": "Avis - Demande de documents",
        "tags": ["documents", "ent", "scolarite"],
    },
    {
        "questions": [
            "C'est quoi l'espace etudiant",
            "A quoi sert l'espace etudiant ENSA BM",
            "Quels services sont disponibles sur l'espace etudiant",
            "Que peut faire un etudiant sur la plateforme espace etudiant",
        ],
        "answer": (
            "L'Espace Etudiant est presente comme le canal officiel de communication entre l'administration "
            "et les etudiants. Il donne acces au tableau de bord personnel, emploi du temps, examens, notes et "
            "resultats, absences, inscription pedagogique, documents administratifs, bibliotheque, bourse et AMO."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/lancement-de-lespace-etudiant-ensa-beni-mellal/",
        "source_title": "Lancement de l'Espace Etudiant",
        "tags": ["espace_etudiant", "services"],
    },
    {
        "questions": [
            "Ou consulter l'emploi du temps",
            "Comment voir mon planning",
            "Ou se trouve le planning des etudiants",
            "Comment acceder a l'EDT de l'ENSA BM",
            "Ou trouver les emplois du temps ENSA Beni Mellal",
        ],
        "answer": (
            "L'emploi du temps peut etre consulte via le portail EDT officiel de l'ENSA Beni Mellal et via "
            "l'Espace Etudiant lorsque la classe ou le compte etudiant est disponible."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/edt/index.php",
        "source_title": "Planning des etudiants",
        "tags": ["edt", "planning"],
    },
    {
        "questions": [
            "Ou consulter les dates d'examens",
            "Comment savoir la salle d'examen",
            "Ou trouver le calendrier des examens",
            "Comment suivre les examens et rattrapages",
        ],
        "answer": (
            "Les dates, horaires et salles d'examen font partie des services annonces dans l'Espace Etudiant. "
            "Les calendriers d'examens sont egalement publies sous forme d'avis sur le site officiel selon les sessions."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/lancement-de-lespace-etudiant-ensa-beni-mellal/",
        "source_title": "Lancement de l'Espace Etudiant",
        "tags": ["examens", "calendrier"],
    },
    {
        "questions": [
            "Ou consulter mes notes",
            "Comment voir mes resultats",
            "Ou trouver les resultats des examens",
            "Comment suivre mes performances academiques",
        ],
        "answer": (
            "La consultation des notes et resultats fait partie des services annonces dans l'Espace Etudiant. "
            "L'etudiant doit donc utiliser son espace ou suivre les avis officiels publies par l'administration."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/lancement-de-lespace-etudiant-ensa-beni-mellal/",
        "source_title": "Lancement de l'Espace Etudiant",
        "tags": ["notes", "resultats"],
    },
    {
        "questions": [
            "Ou consulter mes absences",
            "Comment savoir mes absences",
            "Comment suivre mon registre de presence",
            "Que faire pour une absence",
        ],
        "answer": (
            "La consultation des absences et du registre de presence fait partie des services de l'Espace Etudiant. "
            "Pour une justification ou une situation particuliere, l'etudiant doit suivre la procedure communiquee "
            "par l'administration ou contacter le service concerne."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/lancement-de-lespace-etudiant-ensa-beni-mellal/",
        "source_title": "Lancement de l'Espace Etudiant",
        "tags": ["absences", "presence"],
    },
    {
        "questions": [
            "Comment faire l'inscription pedagogique",
            "Ou gerer mes inscriptions aux modules",
            "Comment s'inscrire aux modules",
            "Ou trouver l'inscription pedagogique",
        ],
        "answer": (
            "L'inscription pedagogique et la gestion des inscriptions aux modules sont annoncees comme des services "
            "de l'Espace Etudiant de l'ENSA Beni Mellal."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/lancement-de-lespace-etudiant-ensa-beni-mellal/",
        "source_title": "Lancement de l'Espace Etudiant",
        "tags": ["inscription_pedagogique", "modules"],
    },
    {
        "questions": [
            "Comment suivre ma bourse",
            "Ou consulter le dossier bourse",
            "Comment acceder a E-Bourse",
            "La bourse est disponible dans quel espace",
        ],
        "answer": (
            "L'Espace Etudiant donne acces au dossier E-Bourse selon l'annonce officielle de lancement de la plateforme."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/lancement-de-lespace-etudiant-ensa-beni-mellal/",
        "source_title": "Lancement de l'Espace Etudiant",
        "tags": ["bourse", "e-bourse"],
    },
    {
        "questions": [
            "Ou trouver les informations AMO",
            "Comment consulter l'assurance maladie obligatoire",
            "L'AMO est disponible ou",
            "Comment suivre mes droits AMO",
        ],
        "answer": (
            "Les informations concernant l'Assurance Maladie Obligatoire (AMO), les droits et remboursements, "
            "font partie des services annonces dans l'Espace Etudiant."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/lancement-de-lespace-etudiant-ensa-beni-mellal/",
        "source_title": "Lancement de l'Espace Etudiant",
        "tags": ["amo", "assurance"],
    },
    {
        "questions": [
            "Comment choisir sa filiere apres le cycle preparatoire",
            "Quand se fait l'orientation vers la filiere ingenieur",
            "Comment remplir les voeux de filiere",
            "Comment se passe le choix de filiere",
        ],
        "answer": (
            "L'orientation vers une filiere ingenieur se fait a la fin du cycle preparatoire. L'etudiant doit suivre "
            "les avis officiels de l'ENSA BM, remplir la fiche de voeux ou la plateforme indiquee, puis l'affectation "
            "depend des filieres ouvertes, du classement et des regles communiquees par l'administration."
        ),
        "category": "orientation",
        "source_url": "https://ensabm.usms.ac.ma/orientation-et-choix-de-la-filiere-ingenieur/",
        "source_title": "Orientation et choix de la filiere ingenieur",
        "tags": ["orientation", "choix_filiere"],
    },
    {
        "questions": [
            "Combien d'annees dure le cycle preparatoire a l'ENSA Beni Mellal",
            "Combine d'anne fait on en cycle preparatoir a l'ENSA Beni Mellal",
            "Quelle est la duree de 2AP",
            "Combien de semestres contient le cycle preparatoire",
            "Le cycle preparatoire dure combien de temps",
        ],
        "answer": (
            "Le cycle preparatoire 2AP a l'ENSA Beni Mellal dure 2 ans, soit quatre semestres. "
            "Il permet d'acquerir les bases scientifiques avant l'orientation vers une filiere ingenieur."
        ),
        "category": "admission",
        "source_url": "https://ensabm.usms.ac.ma/api/",
        "source_title": "Cycle preparatoire 2AP",
        "tags": ["2ap", "cycle_preparatoire", "duree"],
    },
    {
        "questions": [
            "Comment rejoindre le cycle preparatoire de l'ENSA Beni Mellal",
            "Comment integrer 2AP a l'ENSA BM",
            "Comment rejoindre l'ENSA Beni Mellal apres le bac",
            "Comment acceder au cycle preparatoire ENSA BM",
            "Quelle est la voie d'admission en 2AP",
        ],
        "answer": (
            "L'acces au cycle preparatoire 2AP se fait selon les avis officiels d'admission ENSA, notamment "
            "apres le bac via le concours ou la procedure nationale annoncee. L'etudiant doit suivre les dates, "
            "conditions et listes publiees par l'ENSA BM et les plateformes officielles."
        ),
        "category": "admission",
        "source_url": "https://ensabm.usms.ac.ma/api/",
        "source_title": "Cycle preparatoire 2AP",
        "tags": ["2ap", "admission", "bac"],
    },
    {
        "questions": [
            "Comment rejoindre le cycle ingenieur de l'ENSA Beni Mellal",
            "Comment integrer le cycle ingenieur a l'ENSA BM",
            "Comment acceder a une filiere ingenieur ENSA BM",
            "Admission parallele cycle ingenieur ENSA Beni Mellal",
            "Comment entrer en filiere ingenieur apres 2AP",
        ],
        "answer": (
            "Pour rejoindre le cycle ingenieur de l'ENSA Beni Mellal, l'etudiant passe normalement par le cycle "
            "preparatoire ENSA puis l'orientation vers une filiere ingenieur. Une admission parallele peut aussi "
            "etre ouverte selon les avis officiels, les conditions de diplome, le dossier et les places disponibles."
        ),
        "category": "admission",
        "source_url": "https://ensabm.usms.ac.ma/orientation-et-choix-de-la-filiere-ingenieur/",
        "source_title": "Orientation et choix de la filiere ingenieur",
        "tags": ["cycle_ingenieur", "admission", "orientation"],
    },
    {
        "questions": [
            "Quel est le contact officiel de l'administration",
            "Comment contacter l'ENSA Beni Mellal",
            "Quel est l'email officiel de l'ecole",
            "Ou envoyer une demande administrative",
        ],
        "answer": (
            "Le contact officiel general indique sur le site est ensabm.contact@usms.ma. Le site officiel est "
            "https://ensabm.usms.ac.ma/ et l'ecole se situe au campus universitaire M'ghila a Beni Mellal."
        ),
        "category": "contact",
        "source_url": BASE_URL,
        "source_title": "ENSA Beni Mellal",
        "tags": ["contact", "email", "administration"],
    },
    {
        "questions": [
            "Que faire si j'ai perdu mon login",
            "Comment recuperer mon compte etudiant",
            "Je n'arrive pas a me connecter a l'espace etudiant",
            "Probleme de connexion ENT que faire",
        ],
        "answer": (
            "Pour un probleme de compte, de login ou d'acces a l'ENT/Espace Etudiant, il faut utiliser les liens "
            "de recuperation indiques sur la plateforme lorsqu'ils existent, puis contacter l'administration ou le "
            "service informatique/scolarite si le probleme persiste."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/2021/12/avis-demande-de-documents/",
        "source_title": "Avis - Demande de documents",
        "tags": ["ent", "compte", "connexion"],
    },
    {
        "questions": [
            "Comment demander une convention de stage",
            "Ou deposer les documents de stage",
            "Qui contacter pour le stage",
            "Comment preparer le PFE administrativement",
        ],
        "answer": (
            "Pour les conventions, documents de stage ou PFE, l'etudiant doit suivre les consignes de sa filiere "
            "et contacter le coordinateur, l'encadrant ou le service administratif concerne. Les pages filieres "
            "indiquent que le PFE est encadre par un tuteur academique et, selon le cas, un tuteur industriel."
        ),
        "category": "stages",
        "source_url": BASE_URL,
        "source_title": "Pages filieres ENSA BM",
        "tags": ["stage", "pfe", "convention"],
    },
    {
        "questions": [
            "Que faire pour une reclamation de note",
            "Comment contester une note",
            "Comment faire une reclamation administrative",
            "Ou deposer une reclamation",
        ],
        "answer": (
            "Pour une reclamation de note ou une reclamation administrative, l'etudiant doit suivre les delais "
            "et la procedure communiques dans l'avis officiel correspondant, utiliser l'Espace Etudiant si la "
            "demarche y est ouverte, ou contacter le service de scolarite/administration."
        ),
        "category": "administration",
        "source_url": "https://ensabm.usms.ac.ma/lancement-de-lespace-etudiant-ensa-beni-mellal/",
        "source_title": "Lancement de l'Espace Etudiant",
        "tags": ["reclamation", "notes"],
    },
]


class MainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.meta_description = ""
        self.current_tag = ""
        self._skip_depth = 0
        self._buffer: list[str] = []
        self.headings: list[str] = []
        self.paragraphs: list[str] = []
        self.lists: list[str] = []
        self.links: set[str] = set()
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = {k.lower(): v or "" for k, v in attrs}
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "meta" and attr.get("name", "").lower() == "description":
            self.meta_description = clean_text(attr.get("content", ""))
        if tag == "a" and attr.get("href"):
            self.links.add(attr["href"])
        if tag in {"h1", "h2", "h3", "h4", "p", "li", "td", "th"}:
            self.current_tag = tag
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag == self.current_tag:
            text = clean_text(" ".join(self._buffer))
            if len(text) >= 3:
                if tag in {"h1", "h2", "h3", "h4"}:
                    self.headings.append(text)
                elif tag == "li":
                    self.lists.append(text)
                else:
                    self.paragraphs.append(text)
            self.current_tag = ""
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        if self.current_tag:
            self._buffer.append(data)


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_for_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:64] or "qa"


def fetch_text(url: str, timeout: int = 7) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        if "text" not in content_type and "json" not in content_type and "xml" not in content_type:
            return ""
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def fetch_binary(url: str, timeout: int = 15) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def same_domain_url(base: str, href: str) -> str | None:
    if not href:
        return None
    absolute = urljoin(base, href)
    absolute, _ = urldefrag(absolute)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != DOMAIN:
        return None
    if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|zip|rar|doc|docx|xls|xlsx|ppt|pptx)$", parsed.path, re.I):
        return None
    return absolute.rstrip("/")


def discover_from_sitemap() -> set[str]:
    urls: set[str] = set()
    candidates = [
        urljoin(BASE_URL, "sitemap.xml"),
        urljoin(BASE_URL, "sitemap_index.xml"),
        urljoin(BASE_URL, "page-sitemap.xml"),
        urljoin(BASE_URL, "post-sitemap.xml"),
    ]
    seen_sitemaps: set[str] = set()

    def visit_sitemap(sitemap_url: str) -> None:
        if sitemap_url in seen_sitemaps:
            return
        seen_sitemaps.add(sitemap_url)
        try:
            xml_text = fetch_text(sitemap_url)
        except Exception:
            return
        if not xml_text.strip():
            return
        try:
            root = ElementTree.fromstring(xml_text.encode("utf-8"))
        except Exception:
            return
        for loc in root.findall(".//{*}loc"):
            loc_text = clean_text(loc.text or "")
            if not loc_text:
                continue
            if loc_text.endswith(".xml"):
                visit_sitemap(loc_text)
            else:
                normalized = same_domain_url(BASE_URL, loc_text)
                if normalized:
                    urls.add(normalized)

    for candidate in candidates:
        visit_sitemap(candidate)
    return urls


def discover_from_wp_api() -> set[str]:
    urls: set[str] = set()
    for resource in ("pages", "posts"):
        for page in range(1, 8):
            api_url = f"{BASE_URL.rstrip('/')}/wp-json/wp/v2/{resource}?per_page=100&page={page}"
            try:
                data = json.loads(fetch_text(api_url))
            except Exception:
                break
            if not isinstance(data, list) or not data:
                break
            for item in data:
                link = item.get("link")
                normalized = same_domain_url(BASE_URL, link)
                if normalized:
                    urls.add(normalized)
    return urls


def crawl_site(max_pages: int = 220) -> list[PageDoc]:
    discovered = {url.rstrip("/") for url in PRIORITY_HTML_URLS}
    discovered |= discover_from_sitemap()
    discovered |= discover_from_wp_api()
    queue = list(sorted(discovered))
    visited: set[str] = set()
    docs: list[PageDoc] = []

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url.lower().endswith(".pdf"):
            continue
        if url in visited:
            continue
        visited.add(url)
        try:
            body = fetch_text(url)
        except Exception:
            continue
        if not body.strip() or "<html" not in body.lower():
            continue

        parser = MainTextParser()
        try:
            parser.feed(body)
        except Exception:
            continue
        for href in parser.links:
            child = same_domain_url(url, href)
            if child and child not in visited and child not in queue:
                queue.append(child)

        title = clean_text(" ".join(parser.title_parts))
        title = re.sub(r"\s*[-|]\s*ENSA.*$", "", title).strip() or (parser.headings[0] if parser.headings else url)
        text_blocks = dedupe_text(parser.headings + parser.paragraphs + parser.lists)
        raw_text = clean_text(" ".join(text_blocks))
        if len(raw_text) < 80:
            continue
        docs.append(
            PageDoc(
                url=url,
                title=title,
                description=parser.meta_description,
                headings=dedupe_text(parser.headings),
                paragraphs=dedupe_text([p for p in parser.paragraphs if len(p) > 25]),
                lists=dedupe_text([p for p in parser.lists if len(p) > 10]),
                raw_text=raw_text,
            )
        )
        time.sleep(0.15)

    return docs


def extract_pdf_doc(url: str) -> PageDoc | None:
    try:
        import pdfplumber

        raw = fetch_binary(url)
        page_texts: list[str] = []
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages[:20]:
                page_text = clean_text(page.extract_text() or "")
                if page_text:
                    page_texts.append(page_text)
        raw_text = clean_text(" ".join(page_texts))
        if len(raw_text) < 80:
            return None
        filename = urlparse(url).path.rsplit("/", 1)[-1]
        title = filename.replace("_", " ").replace("-", " ").replace(".pdf", "").strip()
        return PageDoc(
            url=url,
            title=title,
            description="Brochure PDF officielle ENSA Beni Mellal",
            headings=[title],
            paragraphs=sentence_chunks(raw_text, max_chars=700),
            lists=[],
            raw_text=raw_text,
        )
    except Exception as exc:
        print(f"PDF ignored: {url} ({exc})")
        return None


def extract_priority_pdf_docs() -> list[PageDoc]:
    docs: list[PageDoc] = []
    for url in PRIORITY_PDF_URLS:
        doc = extract_pdf_doc(url)
        if doc:
            docs.append(doc)
        time.sleep(0.1)
    return docs


def dedupe_text(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = clean_text(item)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def sentence_chunks(text: str, max_chars: int = 520) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = clean_text(sentence)
        if len(sentence) < 35:
            continue
        if len(current) + len(sentence) > max_chars and current:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def answer_from_text(text: str, limit: int = 750) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].strip() + "."


def qa_id(question: str, answer: str) -> str:
    digest = hashlib.sha1(f"{question}\n{answer}".encode("utf-8")).hexdigest()[:12]
    return f"ensabm-{digest}"


def add_item(items: list[dict], question: str, answer: str, categorie: str, source_url: str, source_title: str, tags: list[str] | None = None) -> None:
    question = clean_text(question).rstrip(" ?") + " ?"
    answer = answer_from_text(answer)
    if len(question) < 8 or len(answer) < 15:
        return
    items.append(
        {
            "id": qa_id(question, answer),
            "question": question,
            "reponse": answer,
            "categorie": categorie,
            "source_url": source_url,
            "source_title": source_title,
            "tags": tags or [],
            "langue": "fr",
            "qualite": "source_officielle_ensabm",
        }
    )


def add_question_variants(
    items: list[dict],
    questions: list[str],
    answer: str,
    categorie: str,
    source_url: str,
    source_title: str,
    tags: list[str] | None = None,
) -> None:
    for question in questions:
        add_item(items, question, answer, categorie, source_url, source_title, tags)


def _semester_label(semester: str) -> str:
    return f"semestre {semester[1:]}" if semester.upper().startswith("S") else semester


def _format_semester_answer(track: str, semester: str, payload: dict) -> str:
    modules = payload.get("modules", [])
    title = payload.get("title", "")
    label = _semester_label(semester)
    answer = f"En {track} {semester} ({label}"
    if title:
        answer += f" - {title}"
    answer += "), les modules sont : " + "; ".join(modules) + "."
    if payload.get("note"):
        answer += f" {payload['note']}"
    return answer


def _normalise_module_name(module: str) -> str:
    cleaned = re.sub(r"\s+", " ", module).strip()
    cleaned = re.sub(r"\s*[:/]\s*", " ", cleaned)
    return cleaned


def generate_structured_program_items() -> list[dict]:
    """Generate clean Q/A entries from official semester programmes."""
    items: list[dict] = []
    for track, semesters in TRACK_SEMESTER_PROGRAMS.items():
        facts = TRACK_FACTS.get(track, {})
        track_name = facts.get("name", track)
        source_title = f"Programme par semestre - {track}"

        for semester, payload in semesters.items():
            semester = semester.upper()
            label = _semester_label(semester)
            modules = payload.get("modules", [])
            answer = _format_semester_answer(track, semester, payload)
            source_url = payload.get("source_url") or facts.get("source_url") or facts.get("url", BASE_URL)
            tags = ["programme", "modules", track.lower(), semester.lower(), "semestre"]

            questions = [
                f"Quels modules sont enseignes en {track} {semester}",
                f"Quels sont les modules de {track} en {semester}",
                f"Quels cours suit la filiere {track} au {label}",
                f"Que fait la filiere {track} lors du {label}",
                f"Programme {track} {semester}",
                f"Programme de la filiere {track} en {label}",
                f"Modules {track} {label}",
                f"Donne les cours de {track} {semester}",
                f"Quels enseignements contient {track} {semester}",
                f"Quels modules fait un etudiant {track} en {label}",
                f"Quels cours sont prevus en {track_name} {semester}",
                f"Que contient le {label} de {track_name}",
            ]

            for alias in TRACK_ALIASES.get(track, [])[:6]:
                questions.extend(
                    [
                        f"Quels modules sont enseignes en {alias} {semester}",
                        f"Quels cours en {alias} au {label}",
                        f"Que fait la filiere {alias} lors du {label}",
                    ]
                )

            add_question_variants(
                items,
                questions,
                answer,
                "programme_semestre",
                source_url,
                source_title,
                tags,
            )

            for module in modules:
                module_clean = _normalise_module_name(module)
                if len(module_clean) < 4 or "projet de fin" in module_clean.lower():
                    continue
                module_answer = (
                    f"Le module {module_clean} est enseigne en {track} {semester} "
                    f"({label}). Dans ce semestre, le programme comprend aussi : "
                    f"{'; '.join(modules)}."
                )
                module_questions = [
                    f"Dans quel semestre {track} fait {module_clean}",
                    f"{module_clean} est enseigne en quel semestre en {track}",
                    f"Le cours {module_clean} est dans quel semestre de {track}",
                    f"En quelle annee ou semestre trouve-t-on {module_clean} en {track}",
                    f"{track} etudie {module_clean} quand",
                    f"Est-ce que {track} fait {module_clean}",
                    f"Ou se trouve le module {module_clean} dans le programme {track}",
                ]
                add_question_variants(
                    items,
                    module_questions,
                    module_answer,
                    "programme_module",
                    source_url,
                    source_title,
                    ["programme", "module", track.lower(), semester.lower(), module_clean.lower()],
                )

    return items


def generate_curated_items() -> list[dict]:
    """Hand-curated official facts extracted from ENSA BM track pages and brochures."""
    items: list[dict] = []
    items.extend(generate_structured_program_items())

    track_list_answer = (
        "Les filieres du cycle ingenieur de l'ENSA Beni Mellal sont : "
        "G2ER (Genie Electrique et Energies Renouvelables), "
        "IAA (Industries AgroAlimentaires), "
        "IACS (Intelligence Artificielle et Cybersecurite) et "
        "TDI (Transformation Digitale Industrielle). Les 2AP correspondent aux deux annees preparatoires."
    )
    add_question_variants(
        items,
        [
            "Quelles sont les filieres du cycle ingenieur a l'ENSA Beni Mellal",
            "Quels sont les filieres disponibles a l'ENSA BM",
            "Cite les filieres de l'ENSA Beni Mellal",
            "Combien de filieres ingenieur existe-t-il a l'ENSA BM",
            "Quelles formations d'ingenieur propose l'ENSA BM",
        ],
        track_list_answer,
        "formation",
        BASE_URL,
        "ENSA Beni Mellal",
        ["filieres", "cycle_ingenieur"],
    )

    for code, facts in TRACK_FACTS.items():
        name = facts["name"]
        short = facts["short_name"]
        source_url = facts.get("source_url", facts["url"])
        source_title = f"Filiere {short} - {name}"
        coordinator = facts["coordinator"]
        email = facts.get("email", "")
        coordinator_answer = f"Le coordinateur de la filiere {short} ({name}) est {coordinator}."
        if email:
            coordinator_answer += f" Contact indique : {email}."

        add_question_variants(
            items,
            [
                f"Qui est le coordinateur de la filiere {short}",
                f"Qui est le coordonnateur de la filiere {short}",
                f"Qui est responsable de la filiere {short}",
                f"Donne le coordinateur {short}",
                f"Coordinateur {short}",
                f"Responsable {short}",
                f"Qui coordonne {short} a l'ENSA Beni Mellal",
                f"Qui est le cooridnateur de la filiere {short}",
                f"Qui est le coordinateur de {name}",
            ],
            coordinator_answer,
            "formation",
            source_url,
            source_title,
            ["coordinateur", short.lower()],
        )

        for alias in TRACK_ALIASES.get(code, []):
            add_question_variants(
                items,
                [
                    f"Qui est le coordinateur de la filiere {alias}",
                    f"Qui est le responsable de {alias}",
                ],
                coordinator_answer,
                "formation",
                source_url,
                source_title,
                ["coordinateur", short.lower(), alias],
            )

        add_question_variants(
            items,
            [
                f"Que signifie {short}",
                f"Quie signife {short}",
                f"Qui signiifie {short}",
                f"Que signife {short}",
                f"{short} veut dire quoi",
                f"C'est quoi {short}",
                f"Explique la filiere {short}",
                f"Presente la filiere {short}",
                f"Quelle est la filiere {short}",
            ],
            f"{short} signifie {name}. {facts['summary']}",
            "formation",
            facts["url"],
            source_title,
            ["definition", short.lower()],
        )

        add_question_variants(
            items,
            [
                f"Quel est l'email du coordinateur de {short}",
                f"Comment contacter le responsable de {short}",
                f"Email coordinateur {short}",
            ],
            f"Le contact indique pour {short} est {email}." if email else f"Aucun email specifique n'est indique pour {short}.",
            "contact",
            source_url,
            source_title,
            ["email", short.lower()],
        )

        add_question_variants(
            items,
            [
                f"Comment acceder a la filiere {short}",
                f"Quelles sont les conditions d'admission en {short}",
                f"Admission {short}",
            ],
            facts["admission"],
            "admission",
            facts["url"],
            source_title,
            ["admission", short.lower()],
        )

        add_question_variants(
            items,
            [
                f"Quels sont les domaines de la filiere {short}",
                f"Quels mots cles retenir pour {short}",
                f"Quels sont les axes de {short}",
            ],
            f"Les principaux domaines de {short} sont : {facts['keywords']}.",
            "formation",
            facts["url"],
            source_title,
            ["domaines", short.lower()],
        )

        detail_items = [
            (
                "duree",
                [
                    f"Quelle est la duree de la filiere {short}",
                    f"Combien d'annees dure {short}",
                    f"Combien de semestres contient {short}",
                ],
                f"La filiere {short} dure {facts.get('duration', '3 ans')} et comprend {facts.get('semesters', 'plusieurs semestres')}.",
            ),
            (
                "credits",
                [
                    f"Combien de credits contient {short}",
                    f"Quel est le volume de credits de {short}",
                    f"{short} contient combien de credits",
                ],
                f"La page officielle indique pour {short} : {facts.get('credits', 'credits non precises dans la fiche synthetique')}.",
            ),
            (
                "langue",
                [
                    f"Quelle est la langue d'enseignement en {short}",
                    f"En quelle langue se fait la filiere {short}",
                    f"Langue d'enseignement {short}",
                ],
                f"La langue ou les langues indiquees pour {short} : {facts.get('language', 'information non precisee dans la fiche synthetique')}.",
            ),
            (
                "mode",
                [
                    f"Quel est le mode d'enseignement de {short}",
                    f"La filiere {short} est en presentiel ou a distance",
                    f"Mode de formation {short}",
                ],
                f"Le mode indique pour {short} : {facts.get('mode', 'information non precisee dans la fiche synthetique')}.",
            ),
            (
                "programme",
                [
                    f"Quel est le programme de la filiere {short}",
                    f"Quels modules sont enseignes en {short}",
                    f"Quels enseignements contient {short}",
                    f"Donne le programme de {short}",
                ],
                facts.get("program", facts["summary"]),
            ),
            (
                "competences",
                [
                    f"Quelles competences developpe la filiere {short}",
                    f"Que va apprendre un etudiant en {short}",
                    f"Quelles sont les competences visees par {short}",
                ],
                facts.get("skills", facts["summary"]),
            ),
            (
                "debouches",
                [
                    f"Quels sont les debouches de {short}",
                    f"Quels metiers apres {short}",
                    f"Que peut faire un laureat de {short}",
                    f"Quels postes apres la filiere {short}",
                ],
                facts.get("jobs", facts["summary"]),
            ),
            (
                "secteurs",
                [
                    f"Quels secteurs recrutent apres {short}",
                    f"Dans quels secteurs travaille un ingenieur {short}",
                    f"Quels sont les secteurs d'activite de {short}",
                ],
                facts.get("sectors", facts["keywords"]),
            ),
            (
                "stages",
                [
                    f"Quels stages sont prevus en {short}",
                    f"La filiere {short} contient quels stages",
                    f"Comment se passe le PFE en {short}",
                ],
                facts.get("stages", "Les stages et le PFE doivent etre suivis selon les consignes officielles de la filiere."),
            ),
            (
                "infrastructures",
                [
                    f"Quels equipements sont disponibles pour {short}",
                    f"Quelles infrastructures utilise la filiere {short}",
                    f"Quels laboratoires pour {short}",
                ],
                facts.get("infrastructure", "Les infrastructures detaillees sont indiquees sur la page officielle de la filiere."),
            ),
            (
                "partenaires",
                [
                    f"Quels sont les partenaires de {short}",
                    f"Quels partenariats pour la filiere {short}",
                    f"La filiere {short} a quels partenaires",
                ],
                facts.get("partners", "Les partenaires sont indiques sur la page officielle de la filiere."),
            ),
        ]

        for detail_tag, questions, answer in detail_items:
            add_question_variants(
                items,
                questions,
                answer,
                "formation",
                facts["url"],
                source_title,
                [detail_tag, short.lower()],
            )

        if facts.get("student_life"):
            add_question_variants(
                items,
                [
                    f"Y a-t-il un club pour la filiere {short}",
                    f"Quel club est associe a {short}",
                    f"Vie etudiante en {short}",
                ],
                facts["student_life"],
                "vie_etudiante",
                facts["url"],
                source_title,
                ["club", short.lower()],
            )

        for person in facts.get("coordinator_variants", []):
            normalized_person = person.title()
            add_question_variants(
                items,
                [
                    f"Qui est {person}",
                    f"Qui est monsieur {person}",
                    f"Quel est le role de {person}",
                ],
                f"{normalized_person} est indique comme coordinateur de la filiere {short} ({name}) a l'ENSA Beni Mellal.",
                "personnes",
                source_url,
                source_title,
                ["personne", "coordinateur", short.lower()],
            )

    add_question_variants(
        items,
        [
            "Qui est monsieur Gouskir",
            "Qui est Gouskir Mohamed",
            "Quel est le role de Mohamed Gouskir",
            "Monsieur Gouskir est responsable de quelle filiere",
            "M Gouskir coordonne quelle filiere",
        ],
        "Pr. Mohamed GOUSKIR est indique dans la brochure officielle comme coordonnateur de la filiere IACS (Intelligence Artificielle et Cybersecurite). Contact indique : m.gouskir@usms.ma.",
        "personnes",
        TRACK_FACTS["IACS"].get("source_url", TRACK_FACTS["IACS"]["url"]),
        "Brochure officielle IACS",
        ["gouskir", "iacs", "coordinateur"],
    )

    for faq in ADMIN_FAQS:
        add_question_variants(
            items,
            faq["questions"],
            faq["answer"],
            faq["category"],
            faq["source_url"],
            faq["source_title"],
            faq["tags"],
        )

    return dedupe_items(items)


def extract_global_facts(docs: list[PageDoc]) -> list[tuple[str, str, str, str, list[str]]]:
    all_text = "\n".join(doc.raw_text for doc in docs)
    home = next((doc for doc in docs if doc.url.rstrip("/") == BASE_URL.rstrip("/")), docs[0] if docs else None)
    source_url = home.url if home else BASE_URL
    source_title = home.title if home else "ENSA Beni Mellal"
    facts: list[tuple[str, str, str, str, list[str]]] = []

    facts.extend(
        [
            (
                "Quel est le nom complet de l'ENSA BM",
                "ENSA BM signifie Ecole Nationale des Sciences Appliquees de Beni Mellal.",
                source_url,
                source_title,
                ["identite", "nom"],
            ),
            (
                "A quelle universite l'ENSA Beni Mellal est-elle rattachee",
                "L'ENSA Beni Mellal est un etablissement public de l'Universite Sultan Moulay Slimane (USMS).",
                source_url,
                source_title,
                ["usms", "universite"],
            ),
            (
                "Quand l'ENSA Beni Mellal a-t-elle ete creee",
                "L'ENSA Beni Mellal a ete creee en 2019.",
                source_url,
                source_title,
                ["creation"],
            ),
            (
                "L'ENSA Beni Mellal fait-elle partie du reseau ENSA Maroc",
                "Oui. L'ENSA Beni Mellal fait partie du reseau ENSA Maroc.",
                source_url,
                source_title,
                ["reseau"],
            ),
            (
                "Ou se situe l'ENSA Beni Mellal",
                "L'ENSA Beni Mellal est situee au Campus universitaire M'ghila, a Beni Mellal.",
                source_url,
                source_title,
                ["localisation", "campus"],
            ),
            (
                "Quel est le site officiel de l'ENSA BM",
                "Le site officiel de l'ENSA BM est https://ensabm.usms.ac.ma/.",
                source_url,
                source_title,
                ["site", "contact"],
            ),
            (
                "Quel est l'email de contact officiel de l'ENSA BM",
                "L'email de contact officiel indique sur le site est ensabm.contact@usms.ma.",
                source_url,
                source_title,
                ["email", "contact"],
            ),
            (
                "Qui est le directeur de l'ENSA BM",
                "Le directeur de l'ENSA Beni Mellal est Pr. BELAID BOUILKHILANE.",
                source_url,
                source_title,
                ["directeur"],
            ),
            (
                "Quelle est la mission de l'ENSA Beni Mellal",
                "La mission de l'ENSA Beni Mellal est de former des ingenieurs de haut niveau capables de s'adapter aux evolutions technologiques et aux besoins du marche de l'emploi.",
                source_url,
                source_title,
                ["mission"],
            ),
            (
                "Comment est structuree la formation initiale a l'ENSA BM",
                "La formation d'ingenieur a l'ENSA BM est structuree en deux annees preparatoires suivies de trois annees de specialisation dans des filieres d'ingenieur.",
                source_url,
                source_title,
                ["formation", "cycle"],
            ),
            (
                "Quelles sont les principales filieres ingenieur de l'ENSA BM",
                "Les filieres ingenieur presentes sur le site de l'ENSA BM comprennent notamment G2ER, IAA, IACS et TDI.",
                source_url,
                source_title,
                ["filieres"],
            ),
        ]
    )

    email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", all_text)
    if email_match:
        facts.append(("Quel email apparait sur le site officiel de l'ENSA BM", f"L'email indique est {email_match.group(0)}.", source_url, source_title, ["email"]))
    return facts


def generate_base_items(docs: list[PageDoc]) -> list[dict]:
    items: list[dict] = []

    items.extend(generate_curated_items())

    for question, answer, source_url, source_title, tags in extract_global_facts(docs):
        add_item(items, question, answer, "informations_generales", source_url, source_title, tags)

    for doc in docs:
        page_category = categorize_page(doc)
        add_item(
            items,
            f"Que contient la page officielle {doc.title}",
            doc.description or " ".join(doc.paragraphs[:3]) or doc.raw_text,
            page_category,
            doc.url,
            doc.title,
            ["page", page_category],
        )
        add_item(
            items,
            f"Ou trouver les informations sur {doc.title}",
            f"Les informations sur {doc.title} sont disponibles sur la page officielle : {doc.url}.",
            "navigation",
            doc.url,
            doc.title,
            ["lien", "navigation"],
        )

        for heading in doc.headings[:18]:
            nearby = related_text_for_heading(doc, heading)
            if nearby:
                add_item(
                    items,
                    f"Que dit l'ENSA BM a propos de {heading}",
                    nearby,
                    page_category,
                    doc.url,
                    doc.title,
                    ["section", heading.lower()],
                )
                add_item(
                    items,
                    f"Explique la section {heading} de la page {doc.title}",
                    nearby,
                    page_category,
                    doc.url,
                    doc.title,
                    ["section", heading.lower()],
                )

        for chunk in sentence_chunks(" ".join(doc.paragraphs[:35] + doc.lists[:35])):
            topic = infer_topic(chunk, doc.title)
            add_item(items, f"Que faut-il savoir sur {topic}", chunk, page_category, doc.url, doc.title, [topic.lower()])
            add_item(items, f"Quelle information donne l'ENSA BM sur {topic}", chunk, page_category, doc.url, doc.title, [topic.lower()])

        add_pattern_items(items, doc)

    return dedupe_items(items)


def categorize_page(doc: PageDoc) -> str:
    text = f"{doc.title} {doc.raw_text}".lower()
    if any(k in text for k in ["filiere", "g2er", "iaa", "iacs", "tdi", "formation"]):
        return "formation"
    if any(k in text for k in ["admission", "inscription", "candidat", "concours"]):
        return "admission"
    if any(k in text for k in ["actualite", "soutenance", "annonce", "avis", "resultat"]):
        return "actualites"
    if any(k in text for k in ["contact", "email", "localisation", "campus"]):
        return "contact"
    if any(k in text for k in ["recherche", "laboratoire", "innovation"]):
        return "recherche"
    return "informations_generales"


def related_text_for_heading(doc: PageDoc, heading: str) -> str:
    blocks = doc.paragraphs + doc.lists
    candidates = [block for block in blocks if any(token in block.lower() for token in key_tokens(heading))]
    if not candidates:
        candidates = blocks[:4]
    return " ".join(candidates[:4])


def key_tokens(text: str) -> list[str]:
    stop = {"les", "des", "une", "pour", "avec", "dans", "notre", "votre", "nous", "vous", "sur", "par"}
    tokens = re.findall(r"[a-zA-Z0-9]{4,}", text.lower())
    return [token for token in tokens if token not in stop][:5]


def infer_topic(chunk: str, fallback: str) -> str:
    tokens = key_tokens(chunk)
    if tokens:
        return " ".join(tokens[:4])
    return fallback


def add_pattern_items(items: list[dict], doc: PageDoc) -> None:
    text = doc.raw_text
    emails = sorted(set(re.findall(r"[\w.+-]+@[\w.-]+\.\w+", text)))
    for email in emails:
        add_item(items, f"Quel email est associe a {doc.title}", f"L'email associe a cette information est {email}.", "contact", doc.url, doc.title, ["email"])

    urls = sorted(set(re.findall(r"https?://[^\s\])>,;]+", text)))
    for url in urls[:10]:
        add_item(items, f"Quel lien officiel est mentionne sur {doc.title}", f"Le lien officiel mentionne est {url.rstrip('.,')}.", "navigation", doc.url, doc.title, ["lien"])

    for code in ["G2ER", "IAA", "IACS", "TDI", "2AP"]:
        if re.search(rf"\b{code}\b", text, re.I):
            add_item(items, f"Que dit la page {doc.title} sur {code}", text, "formation", doc.url, doc.title, [code.lower()])

    coordinator = re.search(r"(Coordinateur|Directeur)\s+([A-Z][A-Za-z.\- ]{4,80})", text)
    if coordinator:
        role = coordinator.group(1)
        name = clean_text(coordinator.group(2))
        add_item(items, f"Qui est le {role.lower()} mentionne dans {doc.title}", f"Le {role.lower()} mentionne est {name}.", "formation", doc.url, doc.title, [role.lower()])

    for year in sorted(set(re.findall(r"\b20\d{2}(?:[–-]20\d{2})?\b", text)))[:12]:
        add_item(items, f"Quelle annee est mentionnee dans {doc.title}", f"La page mentionne l'annee {year}.", categorize_page(doc), doc.url, doc.title, ["annee"])


def dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = re.sub(r"\W+", " ", item["question"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


VARIANT_TEMPLATES = [
    "{q}",
    "Peux-tu me dire : {q}",
    "Je suis etudiant, {q}",
    "Pour un etudiant de l'ENSA BM, {q}",
    "J'ai besoin d'une reponse claire : {q}",
    "Donne une reponse courte : {q}",
    "Explique simplement : {q}",
    "En contexte ENSA Beni Mellal, {q}",
    "Dans le site officiel ENSA BM, {q}",
    "Selon l'ENSA BM, {q}",
    "Je prepare mon dossier, {q}",
    "Je suis nouveau a l'ENSA BM, {q}",
    "Question etudiante : {q}",
    "Pour la soutenance ou l'orientation, {q}",
    "Reponds sans inventer : {q}",
]


def expand_variants(base_items: list[dict], target_count: int) -> list[dict]:
    expanded: list[dict] = []
    seen: set[str] = set()

    def push(item: dict, question: str) -> None:
        q = clean_text(question).rstrip("?") + " ?"
        key = re.sub(r"\W+", " ", q.lower()).strip()
        if key in seen:
            return
        seen.add(key)
        clone = dict(item)
        clone["question"] = q
        clone["id"] = qa_id(q, clone["reponse"])
        expanded.append(clone)

    for item in base_items:
        push(item, item["question"])

    idx = 0
    while len(expanded) < target_count and base_items:
        item = base_items[idx % len(base_items)]
        template = VARIANT_TEMPLATES[(idx // len(base_items)) % len(VARIANT_TEMPLATES)]
        q = template.format(q=item["question"].rstrip(" ?"))
        push(item, q)
        idx += 1
        if idx > target_count * 8:
            break

    return expanded[:target_count]


def generate_student_questions(base_items: list[dict], docs: list[PageDoc], target_additional: int = 2000) -> list[dict]:
    """Generate additional student-like questions using Groq to anticipate common queries."""
    additional_items: list[dict] = []
    seen_questions: set[str] = set()

    # Collect all existing questions for deduplication
    for item in base_items:
        seen_questions.add(re.sub(r"\W+", " ", item["question"].lower()).strip())

    # Sample content from docs for prompts
    sample_texts = []
    for doc in docs[:10]:  # Use first 10 docs
        sample_texts.append(f"Page: {doc.title}\nContent: {doc.raw_text[:1000]}")

    combined_content = "\n\n".join(sample_texts)

    prompt = f"""
Tu es un assistant expert en génération de FAQ pour étudiants de l'ENSA Beni Mellal.
Basé sur le contenu officiel scrapé du site ENSA BM ci-dessous, génère {target_additional} paires question-réponse supplémentaires.

Le contenu scrapé :
{combined_content}

Instructions :
- Génère des questions qu'un étudiant pourrait poser, en te mettant dans la peau d'un étudiant.
- Anticipe toutes les questions possibles : admission, formation, vie étudiante, contacts, filières, etc.
- Les questions doivent être en français, naturelles et variées.
- Les réponses doivent être basées sur le contenu officiel, précises et utiles.
- Évite les questions déjà couvertes dans la liste existante.
- Format : Une liste JSON de objets avec "question" et "reponse".

Exemples de questions étudiantes :
- "Comment s'inscrire à l'ENSA BM ?"
- "Quels sont les horaires des cours ?"
- "Où manger sur le campus ?"
- "Comment contacter le directeur ?"

Génère au moins {target_additional} paires.
"""

    try:
        system = "Tu es un assistant IA qui génère des FAQ basées sur du contenu officiel. Réponds uniquement avec du JSON valide."
        response = call_groq(prompt, system=system, timeout=60, max_tokens=8000)
        if response:
            # Parse the JSON response
            generated = json.loads(response)
            for qa in generated:
                question = clean_text(qa.get("question", "")).rstrip("?") + " ?"
                answer = answer_from_text(qa.get("reponse", ""))
                key = re.sub(r"\W+", " ", question.lower()).strip()
                if key not in seen_questions and len(question) > 8 and len(answer) > 15:
                    seen_questions.add(key)
                    additional_items.append({
                        "id": qa_id(question, answer),
                        "question": question,
                        "reponse": answer,
                        "categorie": "etudiant_anticipation",
                        "source_url": BASE_URL,
                        "source_title": "Génération IA basée sur contenu officiel",
                        "tags": ["ia_generated", "student_focus"],
                        "langue": "fr",
                        "qualite": "ia_enhanced_officiel",
                    })
    except Exception as e:
        print(f"Erreur lors de la génération IA : {e}")

    return additional_items[:target_additional]


def write_json(items: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def pdf_escape(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return text


def to_pdf_text(text: str) -> str:
    return text.encode("cp1252", errors="replace").decode("cp1252")


def write_simple_pdf(items: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "FAQ officielle enrichie - ENSA Beni Mellal",
        f"Nombre de questions/reponses : {len(items)}",
        f"Source principale : {BASE_URL}",
        "",
    ]
    for idx, item in enumerate(items, start=1):
        lines.append(f"{idx}. Q: {item['question']}")
        lines.extend(f"   A: {part}" for part in textwrap.wrap(item["reponse"], width=105))
        lines.append(f"   Source: {item.get('source_url', '')}")
        lines.append("")

    page_lines = 48
    pages = [lines[i:i + page_lines] for i in range(0, len(lines), page_lines)]
    objects: list[str] = []

    def add_object(body: str) -> int:
        objects.append(body)
        return len(objects)

    font_obj = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_objs: list[int] = []
    for page_no, page in enumerate(pages, start=1):
        stream_parts = ["BT", "/F1 9 Tf", "50 800 Td", "12 TL"]
        for line in page:
            stream_parts.append(f"({pdf_escape(to_pdf_text(line))}) Tj")
            stream_parts.append("T*")
        stream_parts.append("ET")
        stream = "\n".join(stream_parts)
        content_obj = add_object(f"<< /Length {len(stream.encode('latin-1', errors='replace'))} >>\nstream\n{stream}\nendstream")
        page_obj = add_object(
            f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_obj} 0 R >> >> /Contents {content_obj} 0 R >>"
        )
        page_objs.append(page_obj)

    kids = " ".join(f"{obj} 0 R" for obj in page_objs)
    pages_obj = add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_objs)} >>")
    catalog_obj = add_object(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>")

    fixed_objects = []
    for obj in objects:
        fixed_objects.append(obj.replace("/Parent 0 0 R", f"/Parent {pages_obj} 0 R"))

    output = ["%PDF-1.4\n"]
    offsets = [0]
    for index, body in enumerate(fixed_objects, start=1):
        offsets.append(sum(len(part.encode("latin-1", errors="replace")) for part in output))
        output.append(f"{index} 0 obj\n{body}\nendobj\n")
    xref_offset = sum(len(part.encode("latin-1", errors="replace")) for part in output)
    output.append(f"xref\n0 {len(fixed_objects) + 1}\n")
    output.append("0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.append(f"{offset:010d} 00000 n \n")
    output.append(
        f"trailer\n<< /Size {len(fixed_objects) + 1} /Root {catalog_obj} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )
    output_path.write_bytes("".join(output).encode("latin-1", errors="replace"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-count", type=int, default=TARGET_COUNT)
    parser.add_argument("--max-pages", type=int, default=220)
    args = parser.parse_args()

    docs = crawl_site(max_pages=args.max_pages)
    docs.extend(extract_priority_pdf_docs())
    if not docs:
        raise RuntimeError("No ENSA BM pages could be scraped.")

    base_items = generate_base_items(docs)
    expanded_items = expand_variants(base_items, args.target_count)
    student_items: list[dict] = []
    items = dedupe_items(expanded_items + student_items)

    json_path = FAQ_DIR / "faq_ensa_bm_officielle_5000.json"
    pdf_path = DOCS_DIR / "faq_ensa_bm_officielle_5000.pdf"
    backend_pdf_path = FAQ_DIR / "faq_ensa_bm_officielle_5000.pdf"
    snapshot_path = DOCS_DIR / "ensabm_scrape_snapshot.json"

    write_json(items, json_path)
    write_simple_pdf(items, pdf_path)
    write_simple_pdf(items, backend_pdf_path)
    write_json(
        [
            {
                "url": doc.url,
                "title": doc.title,
                "description": doc.description,
                "headings": doc.headings,
                "text_preview": doc.raw_text[:1200],
            }
            for doc in docs
        ],
        snapshot_path,
    )

    print(f"Scraped pages: {len(docs)}")
    print(f"Base QA items: {len(base_items)}")
    print(f"Expanded QA items: {len(expanded_items)}")
    print(f"Student AI QA items: {len(student_items)}")
    print(f"Final QA items: {len(items)}")
    print(f"JSON: {json_path}")
    print(f"PDF: {pdf_path}")
    print(f"Backend PDF: {backend_pdf_path}")
    print(f"Snapshot: {snapshot_path}")


if __name__ == "__main__":
    main()
