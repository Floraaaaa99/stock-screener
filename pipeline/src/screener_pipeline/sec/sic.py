"""SEC Standard Industrial Classification (SIC) codes and major-group labels.

SIC codes and descriptions come from each company's EDGAR submissions JSON (`sic`,
`sicDescription`). Major-group titles are the two-digit groups from the U.S. SIC manual.
They are not Yahoo sectors or industries.
"""

from __future__ import annotations

from dataclasses import dataclass

# Two-digit SIC major groups (U.S. SIC manual). Used only as a filter roll-up.
SIC_MAJOR_GROUPS: dict[str, str] = {
    "01": "Agricultural Production — Crops",
    "02": "Agricultural Production — Livestock",
    "07": "Agricultural Services",
    "08": "Forestry",
    "09": "Fishing, Hunting, and Trapping",
    "10": "Metal Mining",
    "12": "Coal Mining",
    "13": "Oil and Gas Extraction",
    "14": "Mining and Quarrying of Nonmetallic Minerals",
    "15": "Building Construction",
    "16": "Heavy Construction",
    "17": "Construction Special Trade Contractors",
    "20": "Food and Kindred Products",
    "21": "Tobacco Products",
    "22": "Textile Mill Products",
    "23": "Apparel and Other Textile Products",
    "24": "Lumber and Wood Products",
    "25": "Furniture and Fixtures",
    "26": "Paper and Allied Products",
    "27": "Printing, Publishing, and Allied Industries",
    "28": "Chemicals and Allied Products",
    "29": "Petroleum Refining and Related Industries",
    "30": "Rubber and Miscellaneous Plastics Products",
    "31": "Leather and Leather Products",
    "32": "Stone, Clay, Glass, and Concrete Products",
    "33": "Primary Metal Industries",
    "34": "Fabricated Metal Products",
    "35": "Industrial and Commercial Machinery and Computer Equipment",
    "36": "Electronic and Other Electrical Equipment",
    "37": "Transportation Equipment",
    "38": "Measuring, Analyzing, and Controlling Instruments",
    "39": "Miscellaneous Manufacturing Industries",
    "40": "Railroad Transportation",
    "41": "Local and Suburban Transit",
    "42": "Motor Freight Transportation and Warehousing",
    "43": "United States Postal Service",
    "44": "Water Transportation",
    "45": "Transportation by Air",
    "46": "Pipelines, Except Natural Gas",
    "47": "Transportation Services",
    "48": "Communications",
    "49": "Electric, Gas, and Sanitary Services",
    "50": "Wholesale Trade — Durable Goods",
    "51": "Wholesale Trade — Nondurable Goods",
    "52": "Building Materials, Hardware, Garden Supply",
    "53": "General Merchandise Stores",
    "54": "Food Stores",
    "55": "Automotive Dealers and Gasoline Service Stations",
    "56": "Apparel and Accessory Stores",
    "57": "Home Furniture, Furnishings, and Equipment Stores",
    "58": "Eating and Drinking Places",
    "59": "Miscellaneous Retail",
    "60": "Depository Institutions",
    "61": "Non-depository Credit Institutions",
    "62": "Security and Commodity Brokers",
    "63": "Insurance Carriers",
    "64": "Insurance Agents, Brokers, and Service",
    "65": "Real Estate",
    "67": "Holding and Other Investment Offices",
    "70": "Hotels, Rooming Houses, Camps",
    "72": "Personal Services",
    "73": "Business Services",
    "75": "Automotive Repair, Services, and Parking",
    "76": "Miscellaneous Repair Services",
    "78": "Motion Pictures",
    "79": "Amusement and Recreation Services",
    "80": "Health Services",
    "81": "Legal Services",
    "82": "Educational Services",
    "83": "Social Services",
    "84": "Museums, Art Galleries, and Botanical Gardens",
    "86": "Membership Organizations",
    "87": "Engineering, Accounting, Research, Management, and Related Services",
    "88": "Private Households",
    "89": "Miscellaneous Services",
    "91": "Executive, Legislative, and General Government",
    "92": "Justice, Public Order, and Safety",
    "93": "Public Finance, Taxation, and Monetary Policy",
    "94": "Administration of Human Resource Programs",
    "95": "Administration of Environmental Quality and Housing Programs",
    "96": "Administration of Economic Programs",
    "97": "National Security and International Affairs",
    "99": "Nonclassifiable Establishments",
}


def normalize_sic(raw: str | int | None) -> str | None:
    if raw is None or raw == "":
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(4)[-4:]


def major_group_name(code: str | None) -> str | None:
    if not code:
        return None
    key = code[:2]
    return SIC_MAJOR_GROUPS.get(key, f"SEC SIC major group {key}")


def industry_label(code: str | None, description: str | None) -> str | None:
    if not code:
        return None
    desc = (description or "").strip()
    return f"{code} — {desc}" if desc else code


@dataclass(frozen=True)
class SicInfo:
    code: str | None
    description: str | None
    major_group: str | None
    label: str | None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "description": self.description,
            "majorGroup": self.major_group,
            "label": self.label,
            "source": "SEC EDGAR submissions",
        }


def sic_from_submissions(payload: dict) -> SicInfo:
    code = normalize_sic(payload.get("sic"))
    desc = (payload.get("sicDescription") or None) if code else None
    if isinstance(desc, str):
        desc = desc.strip() or None
    return SicInfo(code, desc, major_group_name(code), industry_label(code, desc))
