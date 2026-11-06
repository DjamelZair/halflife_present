"""Where the Lab story draws each transporter's door.

The FDA table does not say this. It is textbook pharmacology and these transporters also work elsewhere,
the story picks the one place each is best known for. Still to be checked by a pharmacist."""

ORGANS = {
    "OAT1": {"organ": "kidney", "other": "Urine"},
    "OAT3": {"organ": "kidney", "other": "Urine"},
    "OCT2": {"organ": "kidney", "other": "Urine"},
    "MATE1": {"organ": "kidney", "other": "Urine"},
    "MATE2-K": {"organ": "kidney", "other": "Urine"},
    "OATP1B1": {"organ": "liver", "other": "Liver"},
    "OATP1B3": {"organ": "liver", "other": "Liver"},
    "P-gp": {"organ": "gut", "other": "Gut"},
    "BCRP": {"organ": "gut", "other": "Gut"},
}
