"""Curated product specifications (target ``dev`` builds the whole product domain).

``product.material``, ``hierarchy``, ``formulation``, ``formulation_ingredient``,
``packaging_spec``, ``label_spec``, ``gtin_registry``, ``product_bom`` and ``bom_line`` are
derived from the SKU master in ``world.SKUS`` so that every specification matches its
product: a sparkling water has no INCI list, a deodorant label follows the EU Cosmetics
Regulation, a GTIN is the SKU's GTIN-13, packaging costs are cents per unit and dimensions
are millimetres of a real-sized pack. Columns that are not set here are filled by the engine.
"""
import datetime
import re
from decimal import Decimal

from . import engine, texts, world

D = Decimal

# --------------------------------------------------------------------------------------
# material master: (code, name, type, group, uom, EUR per uom, kg per uom, litres per uom,
#                   allergen info, storage temp C, shelf life days, country of origin, hazardous)
# --------------------------------------------------------------------------------------
_RAW = [
    ("RM-1001", "Rolled oats", "GRAINS", "KG", "0.62", "1.000", None, "Contains gluten (oats)", 15, 365, "SWE", False),
    ("RM-1002", "Whole rye flour", "GRAINS", "KG", "0.48", "1.000", None, "Contains gluten (rye)", 15, 270, "SWE", False),
    ("RM-1003", "Wheat flour", "GRAINS", "KG", "0.45", "1.000", None, "Contains gluten (wheat)", 15, 270, "DEU", False),
    ("RM-1004", "Buckwheat flour", "GRAINS", "KG", "1.35", "1.000", None, "No allergens declared", 15, 270, "POL", False),
    ("RM-1005", "Sesame seeds", "SEEDS", "KG", "2.90", "1.000", None, "Contains sesame", 15, 365, "IND", False),
    ("RM-1006", "Sunflower seeds", "SEEDS", "KG", "1.60", "1.000", None, "No allergens declared", 15, 365, "BGR", False),
    ("RM-1007", "Lingonberries IQF", "FRUIT", "KG", "3.80", "1.000", None, "No allergens declared", -18, 540, "SWE", False),
    ("RM-1008", "Blueberries IQF", "FRUIT", "KG", "4.20", "1.000", None, "No allergens declared", -18, 540, "FIN", False),
    ("RM-1009", "Cloudberries IQF", "FRUIT", "KG", "14.50", "1.000", None, "No allergens declared", -18, 540, "FIN", False),
    ("RM-1010", "Strawberries IQF", "FRUIT", "KG", "3.10", "1.000", None, "No allergens declared", -18, 540, "POL", False),
    ("RM-1011", "Sea buckthorn puree", "FRUIT", "KG", "5.40", "1.000", None, "No allergens declared", -18, 365, "FIN", False),
    ("RM-1012", "Cane sugar", "SWEETENERS", "KG", "0.85", "1.000", None, "No allergens declared", 20, 730, "BRA", False),
    ("RM-1013", "Honey", "SWEETENERS", "KG", "5.60", "1.000", None, "No allergens declared", 20, 730, "SWE", False),
    ("RM-1014", "Rapeseed oil", "OILS", "L", "1.45", "0.920", "1.000", "No allergens declared", 20, 365, "SWE", False),
    ("RM-1015", "Almonds sliced", "NUTS", "KG", "7.40", "1.000", None, "Contains almonds (tree nuts)", 15, 365, "ESP", False),
    ("RM-1016", "Sea salt", "MINERALS", "KG", "0.30", "1.000", None, "No allergens declared", 20, 1825, "FRA", False),
    ("RM-1017", "Cinnamon ground", "SPICES", "KG", "9.50", "1.000", None, "No allergens declared", 20, 730, "LKA", False),
    ("RM-1018", "Dark chocolate drops", "CHOCOLATE", "KG", "6.80", "1.000", None, "Contains milk; may contain nuts", 16, 365, "BEL", False),
    ("RM-1019", "Apple pieces dried", "FRUIT", "KG", "6.20", "1.000", None, "No allergens declared", 20, 365, "POL", False),
    ("RM-1020", "Pectin", "ADDITIVES", "KG", "11.00", "1.000", None, "No allergens declared", 20, 730, "DNK", False),
    ("RM-1021", "Enzyme alpha-amylase", "ADDITIVES", "KG", "28.00", "1.000", None, "No allergens declared", 5, 365, "DNK", False),
    ("RM-1022", "Calcium carbonate", "MINERALS", "KG", "0.90", "1.000", None, "No allergens declared", 20, 1825, "DEU", False),
    ("RM-1023", "Vitamin D2 premix", "ADDITIVES", "KG", "45.00", "1.000", None, "No allergens declared", 15, 365, "NLD", False),
    ("RM-1024", "Lemon flavour natural", "FLAVOURS", "KG", "18.00", "1.000", None, "No allergens declared", 15, 365, "DEU", False),
    ("RM-1025", "Lime flavour natural", "FLAVOURS", "KG", "18.50", "1.000", None, "No allergens declared", 15, 365, "DEU", False),
    ("RM-1026", "Elderflower extract", "FLAVOURS", "KG", "22.00", "1.000", None, "No allergens declared", 15, 365, "SWE", False),
    ("RM-1027", "Apple juice concentrate", "JUICE_CONC", "KG", "1.70", "1.000", None, "No allergens declared", 5, 365, "POL", False),
    ("RM-1028", "Orange juice concentrate", "JUICE_CONC", "KG", "2.40", "1.000", None, "No allergens declared", -18, 540, "BRA", False),
    ("RM-1029", "Blackcurrant concentrate", "JUICE_CONC", "KG", "3.10", "1.000", None, "No allergens declared", 5, 365, "POL", False),
    ("RM-1030", "Lingonberry juice concentrate", "JUICE_CONC", "KG", "4.60", "1.000", None, "No allergens declared", 5, 365, "SWE", False),
    ("RM-1031", "CO2 food grade", "GASES", "KG", "0.25", "1.000", None, "No allergens declared", 20, 1825, "SWE", True),
    ("RM-1032", "Sodium laureth sulfate", "SURFACTANTS", "KG", "1.90", "1.000", None, "No allergens declared", 20, 730, "DEU", True),
    ("RM-1033", "Cocamidopropyl betaine", "SURFACTANTS", "KG", "2.30", "1.000", None, "No allergens declared", 20, 730, "DEU", False),
    ("RM-1034", "Glycerin", "HUMECTANTS", "KG", "1.40", "1.000", None, "No allergens declared", 20, 1095, "NLD", False),
    ("RM-1035", "Birch leaf extract", "BOTANICALS", "KG", "26.00", "1.000", None, "No allergens declared", 15, 730, "FIN", False),
    ("RM-1036", "Oat kernel extract", "BOTANICALS", "KG", "21.00", "1.000", None, "Contains oats", 15, 730, "SWE", False),
    ("RM-1037", "Juniper oil", "FRAGRANCE", "KG", "85.00", "1.000", None, "Contains fragrance allergens (limonene)", 15, 730, "FIN", True),
    ("RM-1038", "Menthol", "FLAVOURS", "KG", "24.00", "1.000", None, "No allergens declared", 20, 1095, "IND", False),
    ("RM-1039", "Sodium fluoride", "ACTIVES", "KG", "9.80", "1.000", None, "No allergens declared", 20, 1825, "DEU", True),
    ("RM-1040", "Hydrated silica", "ABRASIVES", "KG", "1.95", "1.000", None, "No allergens declared", 20, 1825, "DEU", False),
    ("RM-1041", "Xylitol", "SWEETENERS", "KG", "4.90", "1.000", None, "No allergens declared", 20, 1095, "FIN", False),
    ("RM-1042", "Shea butter", "EMOLLIENTS", "KG", "4.40", "1.000", None, "No allergens declared", 20, 730, "GHA", False),
    ("RM-1043", "Panthenol", "ACTIVES", "KG", "19.00", "1.000", None, "No allergens declared", 20, 1095, "DEU", False),
    ("RM-1044", "Fragrance Arctic Mint", "FRAGRANCE", "KG", "38.00", "1.000", None, "Contains fragrance allergens (limonene, linalool)", 15, 730, "FRA", True),
    ("RM-1045", "Fragrance Lingonberry", "FRAGRANCE", "KG", "41.00", "1.000", None, "Contains fragrance allergens (citral)", 15, 730, "FRA", True),
    ("RM-1046", "Fragrance Fresh Cedar", "FRAGRANCE", "KG", "44.00", "1.000", None, "Contains fragrance allergens (linalool)", 15, 730, "FRA", True),
    ("RM-1047", "Ethanol denatured", "SOLVENTS", "L", "1.10", "0.790", "1.000", "No allergens declared", 20, 1825, "SWE", True),
    ("RM-1048", "Propellant butane-propane", "GASES", "KG", "1.80", "1.000", None, "No allergens declared", 20, 1825, "NLD", True),
]
_PACK = [  # code, name, group, EUR per piece, kg per piece, litres capacity
    ("PM-2001", "Crispbread carton 250 g", "CARTONS", "0.055", "0.022", None),
    ("PM-2002", "Granola stand-up pouch 450 g", "FLEXIBLES", "0.075", "0.012", None),
    ("PM-2003", "Flow-wrap film bar 30 g", "FLEXIBLES", "0.006", "0.001", None),
    ("PM-2004", "Porridge carton 500 g", "CARTONS", "0.048", "0.026", None),
    ("PM-2005", "Porridge sachet 35 g", "FLEXIBLES", "0.009", "0.002", None),
    ("PM-2006", "Glass jar 340 g", "GLASS", "0.140", "0.190", "0.300"),
    ("PM-2007", "Twist-off lid 70 mm", "CLOSURES", "0.035", "0.008", None),
    ("PM-2008", "Aluminium can 330 ml", "CANS", "0.075", "0.013", "0.330"),
    ("PM-2009", "PET bottle 1.5 L", "BOTTLES", "0.062", "0.038", "1.500"),
    ("PM-2010", "Screw cap 28 mm", "CLOSURES", "0.012", "0.002", None),
    ("PM-2011", "Carton 1 L aseptic", "CARTONS", "0.085", "0.028", "1.000"),
    ("PM-2012", "Carton 250 ml aseptic", "CARTONS", "0.045", "0.010", "0.250"),
    ("PM-2013", "Shrink film multipack", "FLEXIBLES", "0.018", "0.015", None),
    ("PM-2014", "Corrugated tray 24", "CARTONS", "0.320", "0.240", None),
    ("PM-2015", "Corrugated shipping case", "CARTONS", "0.280", "0.220", None),
    ("PM-2016", "HDPE bottle 250 ml", "BOTTLES", "0.058", "0.022", "0.250"),
    ("PM-2017", "HDPE bottle 500 ml", "BOTTLES", "0.085", "0.034", "0.500"),
    ("PM-2018", "Refill pouch 750 ml", "FLEXIBLES", "0.095", "0.014", "0.750"),
    ("PM-2019", "Laminate tube 75 ml", "TUBES", "0.072", "0.009", "0.075"),
    ("PM-2020", "Roll-on bottle 50 ml", "BOTTLES", "0.065", "0.012", "0.050"),
    ("PM-2021", "Deodorant stick barrel", "BOTTLES", "0.090", "0.018", None),
    ("PM-2022", "Aerosol can 150 ml", "CANS", "0.210", "0.035", "0.150"),
    ("PM-2023", "Folding carton gift set", "CARTONS", "0.380", "0.085", None),
    ("PM-2024", "Pump dispenser 28 mm", "CLOSURES", "0.110", "0.015", None),
    ("PM-2025", "Flip-top cap 24 mm", "CLOSURES", "0.022", "0.004", None),
    ("PM-2026", "Paper label wrap-around", "LABELS", "0.008", "0.001", None),
    ("PM-2027", "Oat drink crate 6 x 1 L", "CARTONS", "0.240", "0.180", None),
    ("PM-2028", "Tube 30 ml travel", "TUBES", "0.048", "0.005", "0.030"),
]
_STORE_TEMP = {"FRUIT": -18}
_RAW_PACKING = {"GRAINS": "25 kg paper bags", "SEEDS": "25 kg paper bags", "FRUIT": "frozen, 10 kg cartons",
                "SWEETENERS": "25 kg bags or 300 kg drums", "OILS": "1 000 L IBC", "NUTS": "10 kg cartons",
                "MINERALS": "25 kg bags", "SPICES": "5 kg bags", "CHOCOLATE": "10 kg cartons", "ADDITIVES": "5 kg tins",
                "FLAVOURS": "25 kg drums", "JUICE_CONC": "aseptic 200 kg drums", "GASES": "bulk tank delivery",
                "SURFACTANTS": "1 000 kg IBC", "HUMECTANTS": "250 kg drums", "BOTANICALS": "5 kg drums",
                "FRAGRANCE": "25 kg drums", "ACTIVES": "25 kg drums", "ABRASIVES": "25 kg bags",
                "EMOLLIENTS": "25 kg cartons", "SOLVENTS": "200 L drums"}

# --------------------------------------------------------------------------------------
# recipes per sub-category: (material name, function, nominal % w/w, inci name or None)
# --------------------------------------------------------------------------------------
_RECIPE = {
    "CRISPBREAD": [("Whole rye flour", "flour base", "91.0", None), ("Sea salt", "seasoning", "1.5", None),
                   ("Sesame seeds", "topping", "6.0", None)],
    "GRANOLA": [("Rolled oats", "cereal base", "58.0", None), ("Cane sugar", "sweetener", "9.0", None),
                ("Rapeseed oil", "baking fat", "8.0", None), ("Honey", "sweetener", "6.0", None),
                ("Almonds sliced", "inclusion", "7.0", None)],
    "SNACKBAR": [("Rolled oats", "cereal base", "48.0", None), ("Honey", "binder", "14.0", None),
                 ("Dark chocolate drops", "inclusion", "12.0", None), ("Rapeseed oil", "fat", "6.0", None)],
    "PORRIDGE": [("Rolled oats", "cereal base", "92.0", None), ("Apple pieces dried", "inclusion", "5.0", None),
                 ("Cinnamon ground", "spice", "1.0", None)],
    "JAM": [("Lingonberries IQF", "fruit", "55.0", None), ("Cane sugar", "sweetener and preservative", "44.0", None),
            ("Pectin", "gelling agent", "0.8", None)],
    "SPARKLING": [("CO2 food grade", "carbonation", "0.7", None), ("Lemon flavour natural", "flavour", "0.08", None)],
    "JUICE": [("Apple juice concentrate", "juice base", "16.0", None),
              ("Blackcurrant concentrate", "juice base", "4.0", None)],
    "OATDRINK": [("Rolled oats", "cereal base", "10.0", None), ("Enzyme alpha-amylase", "processing aid", "0.05", None),
                 ("Rapeseed oil", "fat", "1.0", None), ("Calcium carbonate", "fortification", "0.3", None),
                 ("Vitamin D2 premix", "fortification", "0.01", None)],
    "HAIRCARE": [("Sodium laureth sulfate", "surfactant", "10.0", "SODIUM LAURETH SULFATE"),
                 ("Cocamidopropyl betaine", "co-surfactant", "3.0", "COCAMIDOPROPYL BETAINE"),
                 ("Glycerin", "humectant", "2.0", "GLYCERIN"), ("Birch leaf extract", "conditioning botanical", "0.5", "BETULA ALBA LEAF EXTRACT")],
    "BODYCARE": [("Sodium laureth sulfate", "surfactant", "9.0", "SODIUM LAURETH SULFATE"),
                 ("Cocamidopropyl betaine", "co-surfactant", "3.5", "COCAMIDOPROPYL BETAINE"),
                 ("Glycerin", "humectant", "3.0", "GLYCERIN"), ("Fragrance Arctic Mint", "fragrance", "0.6", "PARFUM")],
    "ORALCARE": [("Hydrated silica", "abrasive", "18.0", "HYDRATED SILICA"), ("Glycerin", "humectant", "20.0", "GLYCERIN"),
                 ("Xylitol", "sweetener", "10.0", "XYLITOL"), ("Sodium fluoride", "anticaries active", "0.32", "SODIUM FLUORIDE"),
                 ("Menthol", "flavour", "0.5", "MENTHOL")],
    "SKINCARE": [("Glycerin", "humectant", "8.0", "GLYCERIN"), ("Shea butter", "emollient", "5.0", "BUTYROSPERMUM PARKII BUTTER"),
                 ("Oat kernel extract", "skin conditioning", "1.0", "AVENA SATIVA KERNEL EXTRACT"),
                 ("Panthenol", "skin conditioning", "1.0", "PANTHENOL")],
    "DEODORANT": [("Ethanol denatured", "solvent", "30.0", "ALCOHOL DENAT."), ("Glycerin", "humectant", "3.0", "GLYCERIN"),
                  ("Fragrance Fresh Cedar", "fragrance", "1.0", "PARFUM")],
}
_CAS = {"Sea salt": ("7647-14-5", "231-598-3"), "Cane sugar": ("57-50-1", "200-334-9"), "Pectin": ("9000-69-5", "232-553-0"),
        "CO2 food grade": ("124-38-9", "204-696-9"), "Calcium carbonate": ("471-34-1", "207-439-9"),
        "Sodium laureth sulfate": ("68585-34-2", "500-234-8"), "Cocamidopropyl betaine": ("61789-40-0", "263-058-8"),
        "Glycerin": ("56-81-5", "200-289-5"), "Hydrated silica": ("7631-86-9", "231-545-4"), "Xylitol": ("87-99-0", "201-788-0"),
        "Sodium fluoride": ("7681-49-4", "231-667-8"), "Menthol": ("89-78-1", "201-939-0"), "Panthenol": ("81-13-0", "201-327-3"),
        "Ethanol denatured": ("64-17-5", "200-578-6"), "Shea butter": ("194043-92-0", None)}

_INCI = {
    "HAIRCARE": "Aqua, Sodium Laureth Sulfate, Cocamidopropyl Betaine, Glycerin, Betula Alba Leaf Extract, Sodium Chloride, Parfum, Citric Acid, Sodium Benzoate",
    "BODYCARE": "Aqua, Sodium Laureth Sulfate, Cocamidopropyl Betaine, Glycerin, Avena Sativa Kernel Extract, Parfum, Citric Acid, Potassium Sorbate",
    "ORALCARE": "Hydrated Silica, Sorbitol, Aqua, Glycerin, Xylitol, Sodium Fluoride, Aroma, Cellulose Gum, Sodium Benzoate",
    "SKINCARE": "Aqua, Glycerin, Butyrospermum Parkii Butter, Cetearyl Alcohol, Avena Sativa Kernel Extract, Panthenol, Parfum",
    "DEODORANT": "Aqua, Alcohol Denat., Glycerin, Hydroxyethylcellulose, Parfum, Triethyl Citrate, Tocopherol",
    "GIFTSET": "See the individual products in the set",
}
_INGREDIENTS = {  # food / beverage ingredient declarations (label text)
    "CRISPBREAD": "Wholegrain rye flour (92 %), water, salt, yeast",
    "GRANOLA": "Rolled oats (58 %), sugar, rapeseed oil, honey, almonds (7 %), dried fruit",
    "SNACKBAR": "Rolled oats (48 %), honey, dark chocolate (12 %) (cocoa mass, sugar, cocoa butter), rapeseed oil",
    "PORRIDGE": "Rolled oats (92 %), dried apple pieces, cinnamon",
    "JAM": "Berries (55 %), sugar, gelling agent (pectin)",
    "SPARKLING": "Carbonated spring water, natural flavouring",
    "JUICE": "Juice from concentrate (100 %)",
    "OATDRINK": "Water, oats (10 %), rapeseed oil, calcium carbonate, salt, vitamin D2",
}


def _allergen(s):
    sub, code = s["subcat"], s["code"]
    if sub == "CRISPBREAD":
        if "GF" in code:
            return "No gluten-containing cereals; may contain sesame"
        return "Contains: rye (gluten)" + (", sesame" if code.split("-")[2] in ("SES", "SEED") else "; may contain sesame")
    if sub == "GRANOLA":
        return "Contains: oats (gluten)" + (", almonds" if "HONEY" in code else "; may contain nuts")
    if sub == "SNACKBAR":
        return "Contains: oats (gluten)" + (", milk" if "CHOC" in code else "; may contain milk")
    if sub == "PORRIDGE":
        return "Contains: oats (gluten)" + (", rye (gluten)" if "RYE" in code else "")
    if sub == "OATDRINK":
        return "Contains: oats"
    if s["category"] == "PERSONAL_CARE":
        if s["flavour"] in ("Unscented",):
            return "Fragrance-free"
        return "Fragrance allergens: limonene, linalool"
    return "No allergens declared"


_BASE_RX = re.compile(r"\s(\d+(\.\d+)?\s?(g|kg|ml|L)|\d+ x [\d.]+ ?(g|L|ml)).*$")


def _base_name(s):
    """Product name without the pack size ('Rye Crispbread 250 g' -> 'Rye Crispbread')."""
    name = _BASE_RX.sub("", s["name"])
    return name.replace(" Family Pack", "").strip()


def _ph(s):
    sub, fl = s["subcat"], s["flavour"]
    return {"HAIRCARE": ("4.0", "5.0") if s["name"].startswith("Conditioner") else ("5.0", "6.0"),
            "BODYCARE": ("5.0", "6.0"), "ORALCARE": ("6.5", "8.0"), "SKINCARE": ("5.0", "6.5"),
            "DEODORANT": ("5.0", "6.5") if s["form"] == "liquid" else (None, None),
            "JUICE": ("3.0", "3.8"), "SPARKLING": ("4.5", "5.5") if fl == "Natural" else ("3.5", "4.5"),
            "OATDRINK": ("6.6", "7.2"), "JAM": ("2.9", "3.4")}.get(sub, (None, None))


def _viscosity(s):
    sub = s["subcat"]
    if sub == "HAIRCARE":
        return ("6000", "12000") if s["name"].startswith("Conditioner") else ("4000", "8000")
    return {"BODYCARE": ("3000", "7000"), "ORALCARE": ("180000", "320000"), "SKINCARE": ("20000", "40000"),
            "DEODORANT": ("800", "1500") if s["form"] == "liquid" else (None, None), "OATDRINK": ("10", "30"),
            "JUICE": ("5", "20"), "JAM": ("25000", "60000")}.get(sub, (None, None))


_SOLIDS = {"CRISPBREAD": "94.0", "GRANOLA": "95.5", "SNACKBAR": "92.0", "PORRIDGE": "90.0", "JAM": "62.0",
           "SPARKLING": "0.8", "JUICE": "11.5", "OATDRINK": "11.0", "HAIRCARE": "14.0", "BODYCARE": "13.0",
           "ORALCARE": "60.0", "SKINCARE": "22.0", "DEODORANT": "8.0", "GIFTSET": None}
_FTYPE = {"CRISPBREAD": "baked dough", "GRANOLA": "baked cereal cluster", "SNACKBAR": "bound cereal bar",
          "PORRIDGE": "dry blend", "JAM": "cooked fruit preparation", "SPARKLING": "carbonated solution",
          "JUICE": "juice blend", "OATDRINK": "enzymatic oat base", "HAIRCARE": "surfactant solution",
          "BODYCARE": "surfactant solution", "ORALCARE": "gel paste", "SKINCARE": "oil-in-water emulsion",
          "DEODORANT": "hydro-alcoholic solution", "GIFTSET": "kit"}
_USE = {"CRISPBREAD": "Bread replacement and snack", "GRANOLA": "Breakfast cereal", "SNACKBAR": "Snack",
        "PORRIDGE": "Breakfast cereal (cooked)", "JAM": "Spread", "SPARKLING": "Beverage", "JUICE": "Beverage",
        "OATDRINK": "Beverage (plant-based dairy alternative)", "HAIRCARE": "Rinse-off hair care",
        "BODYCARE": "Rinse-off body care", "ORALCARE": "Oral care", "SKINCARE": "Leave-on skin care",
        "DEODORANT": "Leave-on underarm care", "GIFTSET": "Gift set of finished products"}
_ACTIVE = {"ORALCARE": ("Sodium fluoride", "0.320"), "SKINCARE": ("Panthenol", "1.000"),
           "DEODORANT": ("Triethyl citrate", "2.000")}
_PRESERVE = {"HAIRCARE": "Sodium benzoate and potassium sorbate", "BODYCARE": "Sodium benzoate and potassium sorbate",
             "ORALCARE": "Sodium benzoate", "SKINCARE": "Phenoxyethanol", "DEODORANT": "Alcohol (self-preserving)",
             "JUICE": "Pasteurised, no preservatives", "OATDRINK": "UHT treated and aseptically filled, no preservatives",
             "SPARKLING": "No preservatives", "JAM": "Pasteurised, high sugar content",
             "GIFTSET": "See individual products"}
_COLOR = {"Rye": "Dark golden brown", "Sesame": "Golden brown with sesame seeds", "Seeds": "Brown with visible seeds",
          "Sourdough": "Golden brown", "Buckwheat": "Grey-brown", "Gingerbread": "Dark brown", "Lingonberry": "Deep red",
          "Blueberry": "Dark blue-purple", "Cloudberry": "Amber orange", "Strawberry rhubarb": "Red",
          "Sea buckthorn": "Bright orange", "Lemon": "Clear, colourless", "Lime": "Clear, colourless",
          "Elderflower": "Clear, colourless", "Natural": "Clear, colourless", "Lingonberry lime": "Clear, light pink",
          "Apple": "Golden yellow", "Orange": "Orange", "Blackcurrant": "Deep purple", "Apple elderflower": "Pale yellow",
          "Spiced berry": "Dark red", "Original": "Pale beige", "Barista": "Pale beige", "Chocolate": "Light brown",
          "Unsweetened": "Pale beige", "Organic": "Pale beige", "Vanilla": "Pale cream", "Birch": "Clear, pale green",
          "Nettle": "Clear, pale green", "Juniper": "Clear, pale blue", "Mild": "Pearlescent white",
          "Arctic mint": "Clear, light blue", "Unscented": "Clear, colourless", "Cloudberry soap": "Pale amber",
          "Fresh mint": "White with blue stripe", "Mild mint": "White", "Peppermint": "White",
          "Oat birch": "White cream", "Fresh": "Translucent white", "Cedar": "White", "Arctic": "Translucent",
          "Honey almond": "Golden brown", "Nordic berries": "Light brown with red berries", "Apple raisin": "Light brown",
          "Dark chocolate": "Brown with chocolate drops", "Cinnamon apple": "Light brown", "Oat": "Light beige",
          "Rye oat": "Grey-beige", "Mixed": "Assorted", "Strawberry": "White with pink stripe"}


def _storage(s):
    if s["code"] == "KK-JCE-BLUESM-075":
        return "Chilled 2-8 C"
    if s["category"] == "FOOD":
        return "Ambient 15-25 C, dry"
    if s["category"] == "BEVERAGE":
        return "Store below 25 C, refrigerate after opening"
    return "Store below 25 C, protect from direct sunlight"


# primary pack: (packaging material code, component_type, height, width, length mm, case qty, label substrate)
def _pack(s):
    code, sub = s["code"], s["subcat"]
    if sub == "CRISPBREAD":
        return ("PM-2001", "carton", 260, 120, 40, 12, "printed carton")
    if sub == "GRANOLA":
        return ("PM-2002", "stand-up pouch", 240, 160, 80, 8, "printed laminate")
    if sub == "SNACKBAR":
        return ("PM-2003", "flow wrap", 150, 110, 40, 16, "printed film")
    if sub == "PORRIDGE":
        return ("PM-2005" if "8X35" in code else "PM-2004", "carton", 190, 140, 60, 10, "printed carton")
    if sub == "JAM":
        return ("PM-2006", "glass jar", 100 if s["content"] <= 340 else 125, 70, 70, 12, "paper label")
    if sub == "SPARKLING":
        if code.endswith("150P"):
            return ("PM-2009", "PET bottle", 315, 90, 90, 6, "PP film label")
        if "24X033" in code:
            return ("PM-2014", "tray", 125, 270, 400, 1, "printed tray")
        if "6X033" in code:
            return ("PM-2013", "shrink multipack", 120, 135, 200, 4, "printed shrink film")
        return ("PM-2008", "can", 115, 66, 66, 24, "direct print on can")
    if sub == "JUICE":
        return ("PM-2011", "carton", 195, 70, 70, 12, "printed carton")
    if sub == "OATDRINK":
        if "6X1L" in code:
            return ("PM-2027", "crate", 210, 220, 150, 1, "printed carton")
        if code.endswith("025"):
            return ("PM-2012", "carton", 110, 52, 40, 27, "printed carton")
        return ("PM-2011", "carton", 195, 70, 70, 12, "printed carton")
    if sub in ("HAIRCARE", "BODYCARE"):
        if "REFILL" in code:
            return ("PM-2018", "pouch", 240, 150, 60, 12, "printed laminate")
        if s["content"] >= 400:
            return ("PM-2017", "HDPE bottle", 200, 75, 50, 12, "PE film label")
        return ("PM-2016", "HDPE bottle", 165, 60, 40, 12, "PE film label")
    if sub == "ORALCARE":
        return ("PM-2019", "laminate tube", 160, 45, 35, 24, "printed laminate")
    if sub == "SKINCARE":
        return ("PM-2028" if s["content"] <= 30 else "PM-2019", "tube", 110 if s["content"] <= 30 else 160, 40, 30, 24,
                "printed laminate")
    if sub == "DEODORANT":
        if s["form"] == "spray":
            return ("PM-2022", "aerosol can", 165, 45, 45, 12, "direct print on can")
        if s["form"] == "stick":
            return ("PM-2021", "stick barrel", 120, 50, 35, 12, "PE film label")
        return ("PM-2020", "roll-on bottle", 110, 45, 45, 12, "PE film label")
    return ("PM-2023", "folding carton", 220, 160, 70, 6, "printed carton")


_PACK_COLOR = {"can": "Printed aluminium", "aerosol can": "Printed aluminium", "glass jar": "Flint (clear)",
               "PET bottle": "Clear", "HDPE bottle": "White", "pouch": "White", "stand-up pouch": "Kraft brown",
               "carton": "White board", "folding carton": "White board", "tray": "Brown kraft", "crate": "Brown kraft",
               "shrink multipack": "Clear printed", "flow wrap": "Printed", "laminate tube": "White", "tube": "White",
               "stick barrel": "White", "roll-on bottle": "White"}
_RECYCLE = {"carton": "PAP-21", "printed carton": "PAP-21", "stand-up pouch": "OTHER-7", "flow wrap": "PP-5",
            "glass jar": "GL-70", "PET bottle": "PET-1", "tray": "PAP-20", "shrink multipack": "LDPE-4",
            "can": "ALU-41", "crate": "PAP-20", "pouch": "OTHER-7", "HDPE bottle": "HDPE-2", "laminate tube": "OTHER-7",
            "tube": "OTHER-7", "aerosol can": "ALU-41", "stick barrel": "PP-5", "roll-on bottle": "PP-5",
            "folding carton": "PAP-21"}
_PCR = {"PET bottle": "30.00", "HDPE bottle": "25.00", "can": "70.00", "aerosol can": "50.00", "glass jar": "60.00",
        "pouch": "0.00", "stand-up pouch": "0.00", "carton": "0.00", "tray": "80.00", "crate": "75.00",
        "shrink multipack": "30.00", "flow wrap": "0.00", "laminate tube": "15.00", "tube": "15.00",
        "stick barrel": "20.00", "roll-on bottle": "20.00", "folding carton": "0.00"}
_PRINT = {"can": "flexographic", "aerosol can": "offset", "glass jar": "flexographic", "PET bottle": "gravure",
          "HDPE bottle": "flexographic", "laminate tube": "offset", "tube": "offset", "carton": "offset",
          "folding carton": "offset", "tray": "flexographic", "crate": "flexographic", "pouch": "gravure",
          "stand-up pouch": "gravure", "flow wrap": "gravure", "shrink multipack": "flexographic",
          "stick barrel": "screen", "roll-on bottle": "screen"}
_GPC = {"CRISPBREAD": "10000174", "GRANOLA": "10000282", "SNACKBAR": "10000047", "PORRIDGE": "10000280",
        "JAM": "10000149", "SPARKLING": "10000232", "JUICE": "10000227", "OATDRINK": "10000229",
        "HAIRCARE": "10000466", "BODYCARE": "10000447", "ORALCARE": "10000453", "SKINCARE": "10000449",
        "DEODORANT": "10000450", "GIFTSET": "10000469"}
_CLAIMS = {"CRISPBREAD": "Wholegrain rye - high in fibre", "GRANOLA": "Baked with Nordic oats",
           "SNACKBAR": "Source of fibre", "PORRIDGE": "100 % wholegrain oats", "JAM": "55 % berries",
           "SPARKLING": "No sugar, no sweeteners", "JUICE": "No added sugar", "OATDRINK": "Vegan, with added calcium",
           "HAIRCARE": "Dermatologically tested", "BODYCARE": "pH skin-neutral", "ORALCARE": "With 1450 ppm fluoride",
           "SKINCARE": "For dry and sensitive hands", "DEODORANT": "48 h freshness", "GIFTSET": "Limited edition"}
_USAGE = {"CRISPBREAD": "Enjoy with your favourite topping.", "GRANOLA": "Serve with milk, yoghurt or oat drink.",
          "SNACKBAR": "Ready to eat.", "PORRIDGE": "Cook 1 dl oats in 2 dl water for 3-5 minutes.",
          "JAM": "Refrigerate after opening and use within 4 weeks.", "SPARKLING": "Best served chilled.",
          "JUICE": "Shake before serving. Refrigerate after opening.", "OATDRINK": "Shake well. Refrigerate after opening.",
          "HAIRCARE": "Apply to wet hair, massage and rinse.", "BODYCARE": "Apply to wet skin, lather and rinse.",
          "ORALCARE": "Brush twice a day for two minutes.", "SKINCARE": "Massage into clean hands as needed.",
          "DEODORANT": "Apply to clean, dry underarms.", "GIFTSET": "See individual products."}
_WARN = {"HAIRCARE": "Avoid contact with eyes. If contact occurs, rinse with water.",
         "BODYCARE": "Avoid contact with eyes.", "SKINCARE": "For external use only.",
         "ORALCARE": "Children under 6 years: use a pea-sized amount under adult supervision. Contains sodium fluoride.",
         "DEODORANT": "Do not apply to broken or irritated skin.", "GIFTSET": "Keep out of reach of children."}


def _net_decl(s):
    if s["uom"] == "units":
        return "%d pcs" % s["pack"]
    unit = {"g": "g", "kg": "kg", "ml": "ml", "L": "L"}[s["uom"]]
    if s["pack"] > 1 and s["uom"] != "units":
        per = s["content"] / s["pack"]
        per_txt = ("%g" % per) if per != int(per) else "%d" % per
        return "%d x %s %s e" % (s["pack"], per_txt, unit)
    return "%s %s e" % (("%g" % s["content"]), unit)


def _ts(d, h=9):
    return datetime.datetime.combine(d, datetime.time(h, 0))


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------

TABLES = ("product.material", "product.hierarchy", "product.formulation", "product.formulation_ingredient",
          "product.packaging_spec", "product.label_spec", "product.gtin_registry", "product.product_bom",
          "product.bom_line")


def generate(reg):
    _materials(reg)
    _hierarchy(reg)
    _formulations(reg)
    _formulation_ingredients(reg)
    _packaging_specs(reg)
    _label_specs(reg)
    _gtin_registry(reg)
    _product_boms(reg)
    _bom_lines(reg)
    # link the SKU master to its hierarchy node
    for row in reg.rows["product.sku"]:
        s = reg.ctx["sku_by_id"][row["sku_id"]]
        row["hierarchy_id"] = reg.ctx["hierarchy_id"][s["subcat"]]


def _materials(reg):
    fqn = "product.material"
    specs = [("raw_material",) + r for r in _RAW] + [("packaging",) + p for p in _PACK]
    pool = reg.alloc(fqn, len(specs))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids, info = {}, {}
    rows = []
    for i, sp in enumerate(specs):
        mtype = sp[0]
        if mtype == "raw_material":
            _, code, name, group, uom, cost, kg, litres, allergen, temp, shelf, origin, haz = sp
            desc = "%s, %s" % (name, _RAW_PACKING[group])
            conv = D("1.000000")
            ptype = "tank" if group == "GASES" else _RAW_PACKING[group].split(",")[-1].strip().split(" ")[-1]
        else:
            _, code, name, group, cost, kg, litres = sp
            uom, allergen, temp, shelf, origin, haz = "EA", "No allergens declared", 20, 1825, "SWE", False
            desc = "%s, delivered on pallets" % name
            conv = D("2400.000000") if group in ("CLOSURES", "LABELS", "CANS", "FLEXIBLES") else D("600.000000")
            ptype = "pallet"
        ids[name] = pool[i]
        info[name] = {"code": code, "uom": uom, "cost": D(cost), "kg": D(kg), "type": mtype, "group": group}
        created = _ts(datetime.date(2015, 3, 2) + datetime.timedelta(days=37 * i), 10)
        gl_comp = "PL01" if group in ("SURFACTANTS", "HUMECTANTS", "BOTANICALS", "FRAGRANCE", "ACTIVES", "ABRASIVES",
                                      "EMOLLIENTS", "SOLVENTS", "TUBES") else "SE01"
        fixed = {
            "material_id": pool[i], "gl_account_id": reg.ctx["gl"][(gl_comp, "1430")], "parent_material_id": None,
            "supplier_id": reg.pick("procurement.supplier", rnd), "allergen_info": allergen, "base_uom": uom,
            "brand_name": None, "code": code, "country_of_origin": origin, "created_timestamp": created,
            "currency_code": "EUR", "description": desc, "ean": None, "gtin": None, "upc": None,
            "effective_from": created.date(), "effective_until": None, "hazardous_flag": haz,
            "lifecycle_stage": "active", "material_group": group, "material_status": "active",
            "material_type": mtype, "name": name, "packaging_type": ptype,
            "regulatory_status": "approved", "shelf_life_days": shelf, "standard_cost": D(cost),
            "storage_temperature_c": D(temp), "unit_conversion_factor": conv,
            "volume_l": D(litres) if litres else None, "weight_kg": D(kg),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=origin if origin in world.CITIES else "SWE"))
    reg.ctx["material_id"] = ids
    reg.ctx["material_info"] = info
    reg.rows[fqn] = rows


def _hierarchy(reg):
    fqn = "product.hierarchy"
    nodes = [("TOTAL", "Fjällmark total", 1, None, None)]
    for code, name, _ in world.TOP_CATEGORIES:
        nodes.append((code, name, 2, "TOTAL", code))
    for code, name, parent, _ in world.SUBCATEGORIES:
        nodes.append((code, name, 3, parent, code))
    pool = reg.alloc(fqn, len(nodes))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = dict((n[0], pool[i]) for i, n in enumerate(nodes))
    brand_of = {"FOOD": "BJORKO", "BEVERAGE": "KALLKALLA", "PERSONAL_CARE": "MJUKCARE"}
    created = _ts(datetime.date(2016, 1, 11))
    rows = []
    for i, (code, name, level, parent, cat) in enumerate(nodes):
        top = code if level == 2 else (parent if level == 3 else None)
        brand = brand_of.get(top)
        path = "Fjällmark total" if level == 1 else ("Fjällmark total/%s" % name if level == 2 else
                                                     "Fjällmark total/%s/%s" % (dict((c[0], c[1]) for c in world.TOP_CATEGORIES)[parent], name))
        pc = top == "PERSONAL_CARE"
        fixed = {
            "hierarchy_id": pool[i], "brand_id": reg.ctx["brand_id"][brand] if brand else None,
            "company_code_id": reg.ctx["company_id"]["SE01"], "parent_hierarchy_id": ids[parent] if parent else None,
            "product_category_id": reg.ctx["category_id"][cat] if cat else None,
            "profit_center_id": reg.ctx["pc"][brand] if brand else reg.ctx["pc"]["GROUP"],
            "approved_date": created.date(), "created_timestamp": created, "effective_from": created.date(),
            "effective_until": None, "division_code": {"FOOD": "FOOD", "BEVERAGE": "BEVG", "PERSONAL_CARE": "PCAR"}.get(top, "GROUP"),
            "gmp_standard": "ISO 22716" if pc else "None", "gpc_brick_code": _GPC.get(code),
            "gpc_brick_name": name if level == 3 else None, "inci_applicable": pc, "is_leaf_node": level == 3,
            "language_code": "en", "level": level, "level_name": {1: "Total", 2: "Category", 3: "Sub-category"}[level],
            "node_code": code, "node_description": ("%s products of %s" % (name, world.BRAND[brand]["name"]) if brand
                                                    else "All Fjällmark products"),
            "node_name": name, "node_status": "active", "path": path, "sort_order": i + 1,
            "regulatory_framework": ("EU Cosmetics Regulation 1223/2009" if pc else
                                     "EU Regulation 178/2002 and 1169/2011" if top else None),
            "plm_lifecycle_stage": "active", "version_number": 1, "cpsc_regulated": False,
            "updated_timestamp": _ts(datetime.date(2025, 11, 4) + datetime.timedelta(days=i), 11),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country="SWE"))
    reg.ctx["hierarchy_id"] = ids
    reg.rows[fqn] = rows


def _plant_cc(s):
    return {"LUND": "SE01PLUN", "NKPG": "SE01PNKP", "TMPR": "FI01PTMP", "POZN": "PL01PPOZ"}[s["plant"]]


def _formulations(reg):
    fqn = "product.formulation"
    pool = reg.alloc(fqn, len(world.SKUS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    rows = []
    for i, s in enumerate(world.SKUS):
        ids[s["code"]] = pool[i]
        pc = s["category"] == "PERSONAL_CARE"
        created = _ts(s["launch"] - datetime.timedelta(days=200 + i % 60), 10)
        ph_min, ph_max = _ph(s)
        v_min, v_max = _viscosity(s)
        active = _ACTIVE.get(s["subcat"])
        if s["subcat"] == "HAIRCARE" and s["flavour"] == "Juniper":
            active = ("Piroctone olamine", "0.500")
        shelf = world.SHELF_LIFE_DAYS[s["subcat"]]
        fixed = {
            "formulation_id": pool[i], "cost_center_id": reg.ctx["cc"][_plant_cc(s)],
            "product_category_id": reg.ctx["category_id"][s["subcat"]], "sku_id": reg.ctx["sku_id"][s["code"]],
            "active_ingredient_name": active[0] if active else None,
            "active_ingredient_pct": D(active[1]) if active else None,
            "allergen_declaration": _allergen(s), "approval_date": (created + datetime.timedelta(days=60)).date(),
            "code": "FRM-%s" % s["code"], "bom_reference_code": "PB-%s" % s["code"],
            "color_description": _COLOR.get(s["flavour"], "Natural colour"), "created_timestamp": created,
            "effective_date": max((created + datetime.timedelta(days=75)).date(), s["launch"] - datetime.timedelta(days=30)),
            "formulation_type": _FTYPE[s["subcat"]], "fragrance_code": None if not pc or s["flavour"] == "Unscented"
            else "FR-%s" % re.sub(r"[^A-Z]", "", s["flavour"].upper())[:10],
            "gmp_compliance_flag": True, "inci_declaration": _INCI.get(s["subcat"]) if pc else None,
            "intended_use": _USE[s["subcat"]], "is_cruelty_free": True if pc else None,
            "is_fragrance_free": (s["flavour"] == "Unscented") if pc else None,
            "is_vegan": not ("HONEY" in s["code"] or "CHOC" in s["code"] or s["subcat"] == "SNACKBAR"),
            "lab_notebook_reference": "LNB-%s-%03d" % (s["plant"], 100 + i), "lifecycle_stage": "approved",
            "name": "%s %s formulation" % (world.BRAND[s["brand"]]["short"], _base_name(s)),
            "obsolescence_date": None, "ph_min": D(ph_min) if ph_min else None, "ph_max": D(ph_max) if ph_max else None,
            "preservative_system": _PRESERVE.get(s["subcat"], "Low water activity, no preservatives"),
            "rd_project_code": "RD-%s-%d" % (s["brand"][:4], s["launch"].year),
            "reach_registration_number": None, "regulatory_approval_status": "approved",
            "regulatory_classification": "cosmetic" if pc else None, "rspo_certified": pc,
            "source_system_code": "PLM_SPEC", "stability_period_months": max(6, shelf // 30) if not pc else 30,
            "storage_condition": _storage(s), "total_solid_content_pct": D(_SOLIDS[s["subcat"]]) if _SOLIDS[s["subcat"]] else None,
            "version_number": "2.%d" % (i % 4), "viscosity_min_cps": D(v_min) if v_min else None,
            "viscosity_max_cps": D(v_max) if v_max else None,
            "last_modified_timestamp": _ts(datetime.date(2025, 9, 1) + datetime.timedelta(days=(i * 5) % 300), 14),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=world.PLANT[s["plant"]]["country"]))
    reg.ctx["formulation_id"] = ids
    reg.rows[fqn] = rows


def _formulation_ingredients(reg):
    """Key ingredients of one representative formulation per sub-category and flavour family."""
    fqn = "product.formulation_ingredient"
    rnd = reg.rng(fqn)
    seen, specs = set(), []
    for s in world.SKUS:
        key = (s["subcat"], s["flavour"])
        if s["subcat"] not in _RECIPE or key in seen:
            continue
        seen.add(key)
        for n, (mat, func, pct, inci) in enumerate(_RECIPE[s["subcat"]], start=1):
            if s["subcat"] == "CRISPBREAD" and mat == "Sesame seeds" and s["flavour"] not in ("Sesame", "Seeds"):
                continue
            if s["subcat"] == "CRISPBREAD" and "GF" in s["code"] and mat == "Whole rye flour":
                mat = "Buckwheat flour"
            if s["subcat"] == "JAM" and mat == "Lingonberries IQF":
                mat = {"Blueberry": "Blueberries IQF", "Cloudberry": "Cloudberries IQF",
                       "Strawberry rhubarb": "Strawberries IQF", "Sea buckthorn": "Sea buckthorn puree"}.get(s["flavour"], mat)
            if s["subcat"] == "SPARKLING" and mat == "Lemon flavour natural":
                if s["flavour"] == "Natural":
                    continue
                mat = {"Lime": "Lime flavour natural", "Elderflower": "Elderflower extract",
                       "Lingonberry lime": "Lime flavour natural"}.get(s["flavour"], mat)
            if s["subcat"] == "HAIRCARE" and s["flavour"] == "Juniper" and mat == "Birch leaf extract":
                mat, inci = "Juniper oil", "JUNIPERUS COMMUNIS FRUIT OIL"
            if s["subcat"] == "BODYCARE" and mat == "Fragrance Arctic Mint" and s["flavour"] in ("Lingonberry", "Cloudberry"):
                mat = "Fragrance Lingonberry"
            if s["subcat"] == "BODYCARE" and mat.startswith("Fragrance") and s["flavour"] == "Unscented":
                continue
            specs.append((s, n, mat, func, pct, inci))
    pool = reg.alloc(fqn, len(specs))
    gen = reg.gen(fqn)
    rows = []
    for i, (s, n, mat, func, pct, inci) in enumerate(specs):
        pc = s["category"] == "PERSONAL_CARE"
        m = reg.ctx["material_info"][mat]
        cas, ec = _CAS.get(mat, (None, None))
        created = _ts(s["launch"] - datetime.timedelta(days=190), 11)
        nominal = D(pct)
        allergen_mat = [r for r in _RAW if r[1] == mat]
        fixed = {
            "formulation_ingredient_id": pool[i], "formulation_id": reg.ctx["formulation_id"][s["code"]],
            "material_id": reg.ctx["material_id"][mat], "supplier_id": reg.pick("procurement.supplier", rnd),
            "allergen_declaration": allergen_mat[0][7] if allergen_mat else "No allergens declared",
            "approved_by": "Quality Assurance", "approved_timestamp": created + datetime.timedelta(days=12),
            "cas_number": cas, "ec_number": ec, "concentration_nominal_pct": nominal,
            "concentration_min_pct": (nominal * D("0.95")).quantize(D("0.000001")),
            "concentration_max_pct": (nominal * D("1.05")).quantize(D("0.000001")), "concentration_uom": "% w/w",
            "created_timestamp": created, "effective_date": created.date(), "expiry_date": None,
            "fda_status": "permitted" if pc else "gras", "inci_name": inci if pc else None,
            "ingredient_function": func, "ingredient_name": mat, "ingredient_status": "approved",
            "is_active_ingredient": mat in ("Sodium fluoride", "Panthenol"), "is_fragrance_allergen": mat.startswith("Fragrance"),
            "is_natural_origin": m["group"] in ("GRAINS", "SEEDS", "FRUIT", "SWEETENERS", "OILS", "NUTS", "SPICES",
                                                "BOTANICALS", "JUICE_CONC", "EMOLLIENTS"),
            "is_palm_derived": mat in ("Sodium laureth sulfate", "Cocamidopropyl betaine", "Glycerin"),
            "is_prohibited_substance": False, "is_restricted_substance": mat in ("Sodium fluoride",),
            "line_number": n, "origin_country_code": [r for r in _RAW if r[1] == mat][0][10],
            "physical_form": "liquid" if m["uom"] == "L" or m["group"] in ("SURFACTANTS", "FRAGRANCE", "JUICE_CONC") else "solid",
            "regulatory_max_concentration_pct": D("0.150000") if mat == "Sodium fluoride" else None,
            "regulatory_limit_reference": ("EU 1223/2009 Annex III/33 (max 0.15 % F)" if mat == "Sodium fluoride" else None),
            "svhc_flag": False, "vegan_status": "non_vegan" if mat in ("Honey", "Dark chocolate drops") else "vegan",
            "ghs_hazard_classification": ("H319 Eye Irrit. 2" if mat == "Sodium laureth sulfate" else
                                          "H301 Acute Tox. 3" if mat == "Sodium fluoride" else
                                          "H225 Flam. Liq. 2" if mat == "Ethanol denatured" else
                                          "H317 Skin Sens. 1" if mat.startswith("Fragrance") or mat == "Juniper oil" else
                                          "Not classified"),
            "grade_specification": "Cosmetic grade (Ph. Eur.)" if pc else "Food grade",
            "natural_origin_index": D("1.0000") if m["group"] in ("GRAINS", "SEEDS", "FRUIT", "SWEETENERS", "OILS",
                                                                   "NUTS", "SPICES", "BOTANICALS", "JUICE_CONC",
                                                                   "EMOLLIENTS") else D("0.0000"),
            "reach_registration_number": ("01-%010d-%02d-%04d" % (2119400000 + i * 37, 20 + i % 60, 1000 + i)
                                          if pc and cas else None),
            "halal_status": "not_applicable" if pc else "not_certified",
            "ifra_compliance_status": "compliant" if mat.startswith("Fragrance") or mat == "Juniper oil" else "not_applicable",
            "reach_registration_status": "registered" if pc or cas else "exempt",
            "supplier_material_code": "%s-S%02d" % (m["code"], 1 + i % 3),
            "updated_timestamp": created + datetime.timedelta(days=30 + i % 200),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=world.PLANT[s["plant"]]["country"]))
    reg.rows[fqn] = rows


def _packaging_specs(reg):
    fqn = "product.packaging_spec"
    pool = reg.alloc(fqn, len(world.SKUS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    rows = []
    for i, s in enumerate(world.SKUS):
        ids[s["code"]] = pool[i]
        mat_code, ctype, h, w, ln, case_qty, _ = _pack(s)
        mat = [p for p in _PACK if p[0] == mat_code][0]
        tare = D(mat[4]) * 1000 * (s["pack"] if ctype in ("shrink multipack",) else 1)
        if ctype in ("tray", "shrink multipack"):
            tare += D("13") * s["pack"]   # cans in the multipack
        net_g = D(str(s["content"])) * (1000 if s["uom"] in ("kg", "L") else 1) if s["uom"] != "units" else D("450")
        created = _ts(s["launch"] - datetime.timedelta(days=150 + i % 40), 9)
        fixed = {
            "packaging_spec_id": pool[i], "manufacturing_facility_id": reg.ctx["plant_id"][s["plant"]],
            "material_id": reg.ctx["material_id"][mat[1]], "sku_id": reg.ctx["sku_id"][s["code"]],
            "supplier_id": reg.pick("procurement.supplier", rnd), "approval_status": "approved",
            "artwork_ref": "ART-%s-V3" % s["code"], "color": _PACK_COLOR.get(ctype, "White"),
            "component_type": ctype, "created_timestamp": created, "currency_code": "EUR", "ean": s["gtin"],
            "effective_date": created.date() + datetime.timedelta(days=30), "expiry_date": None,
            "finish": rnd.choice(["matte", "gloss"]), "gross_weight_g": (net_g + tare).quantize(D("0.001")),
            "gtin": s["gtin"], "hazmat_flag": ctype == "aerosol can", "height_mm": D(h), "length_mm": D(ln),
            "width_mm": D(w), "hi": 5 + i % 4, "ti": 8 + i % 5, "is_fsc_certified": ctype in ("carton", "tray", "crate", "folding carton"),
            "is_rspo_certified": False, "lead_time_days": 21 + (i * 3) % 28, "lifecycle_status": "active",
            "moq": 10000 * (1 + i % 5), "packaging_level": "primary", "pcr_content_pct": D(_PCR[ctype]),
            "print_method": _PRINT[ctype], "qty_per_parent": case_qty, "recyclability_code": _RECYCLE[ctype],
            "regulatory_compliance_flag": True, "spec_code": "PS-%s" % s["code"],
            "spec_name": "%s primary %s" % (s["full_name"], ctype), "supplier_tooling_ref": "TL-%s" % mat_code,
            "tare_weight_g": tare.quantize(D("0.001")),
            "unit_cost": (D(mat[3]) * (s["pack"] if ctype == "shrink multipack" else 1) +
                          (D("0.075") * s["pack"] if ctype in ("tray", "shrink multipack") else D(0))).quantize(D("0.000001")),
            "upc": None, "version_number": "3.%d" % (i % 3),
            "last_modified_timestamp": _ts(datetime.date(2025, 10, 6) + datetime.timedelta(days=(i * 7) % 300), 13),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=world.PLANT[s["plant"]]["country"]))
    reg.ctx["packaging_spec_id"] = ids
    reg.rows[fqn] = rows


def _label_specs(reg):
    fqn = "product.label_spec"
    pool = reg.alloc(fqn, len(world.SKUS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    rows = []
    for i, s in enumerate(world.SKUS):
        pc = s["category"] == "PERSONAL_CARE"
        _, ctype, h, w, ln, _, substrate = _pack(s)
        created = _ts(s["launch"] - datetime.timedelta(days=120 + i % 30), 10)
        approved = (created + datetime.timedelta(days=21)).date()
        fixed = {
            "label_spec_id": pool[i], "company_code_id": reg.ctx["company_id"]["SE01"],
            "manufacturing_facility_id": reg.ctx["plant_id"][s["plant"]],
            "packaging_spec_id": reg.ctx["packaging_spec_id"][s["code"]], "sku_id": reg.ctx["sku_id"][s["code"]],
            "allergen_declaration": _allergen(s), "approval_status": "approved",
            "artwork_file_reference": "ART-%s-V3.pdf" % s["code"], "barcode_placement": "Back panel, bottom right",
            "barcode_type": "EAN-13", "certification_marks": ("Nordic Swan Ecolabel" if pc else "Vegan label"
                                                                if s["subcat"] == "OATDRINK" else "Keyhole label"
                                                                if s["subcat"] in ("CRISPBREAD", "PORRIDGE") else "None"),
            "claim_text": _CLAIMS[s["subcat"]], "color_profile": "CMYK + 1 Pantone",
            "country_of_origin": world.PLANT[s["plant"]]["country"], "created_timestamp": created,
            "digital_watermark_enabled": False, "distributor_name": "Fjällmark Consumer Goods AB, Stockholm, Sweden",
            "effective_date": max(approved, s["launch"] - datetime.timedelta(days=14)), "expiry_date": None,
            "gtin": "0" + s["gtin"], "ingredient_declaration_text": _INCI.get(s["subcat"]) if pc else _INGREDIENTS.get(s["subcat"]),
            "is_primary_label": True, "label_approval_date": approved,
            "label_dimensions": "%d x %d mm" % (min(h, 220), min(2 * (w + ln), 260)),
            "label_type": "back_of_pack", "label_version": "3.%d" % (i % 3), "language_code": "sv",
            "lot_code_format": "LYYDDD-HHMM", "market_country_code": "SWE",
            "mandatory_regulatory_statements": ("Keep out of reach of children" if pc else "Best before end: see top of pack"),
            "net_content_declaration": _net_decl(s), "nutrition_facts_required": not pc,
            "plm_change_order_number": "ECO-%05d" % (1200 + i), "print_process": _PRINT[ctype] if _PRINT[ctype] in
            ("flexographic", "digital", "offset", "gravure", "screen") else "offset",
            "recycling_symbol_code": _RECYCLE[ctype],
            "regulatory_framework": "EU Cosmetics Regulation 1223/2009" if pc else "EU Regulation 1169/2011 (food information)",
            "regulatory_registration_number": ("CPNP-%07d" % (3100000 + i * 17)) if pc else None,
            "shelf_life_statement": ("Period after opening: 12 months (12M)" if pc else
                                     "Best before: see top of pack. %d days shelf life from production"
                                     % world.SHELF_LIFE_DAYS[s["subcat"]]),
            "substrate_material": substrate, "usage_instructions": _USAGE[s["subcat"]],
            "veeva_document_reference": "VV-LBL-%05d" % (5000 + i),
            "warning_statements": _WARN.get(s["subcat"]) if pc else None,
            "last_modified_timestamp": _ts(datetime.date(2025, 8, 18) + datetime.timedelta(days=(i * 5) % 300), 15),
        }
        if s["form"] == "spray":
            fixed["warning_statements"] = ("Extremely flammable aerosol. Pressurised container: may burst if heated. "
                                           "Keep away from heat and direct sunlight.")
        rows.append(gen.row(i, rnd, fixed, anchor=created, country="SWE"))
    reg.rows[fqn] = rows


def _gtin_registry(reg):
    fqn = "product.gtin_registry"
    pool = reg.alloc(fqn, len(world.SKUS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    rows = []
    for i, s in enumerate(world.SKUS):
        _, ctype, _, _, _, case_qty, _ = _pack(s)
        assigned = s["launch"] - datetime.timedelta(days=180 + i % 30)
        created = _ts(assigned, 9)
        cat_name = dict((c[0], c[1]) for c in world.TOP_CATEGORIES)[s["category"]]
        fixed = {
            "gtin_registry_id": pool[i], "brand_id": reg.ctx["brand_id"][s["brand"]],
            "company_code_id": reg.ctx["company_id"]["SE01"], "sku_id": reg.ctx["sku_id"][s["code"]],
            "activation_date": s["launch"] - datetime.timedelta(days=30), "assignment_date": assigned,
            "barcode_symbology": "EAN-13", "brand_owner_gln": world.gtin13("7350098", 1),
            "cases_per_pallet": 40 + (i % 5) * 10, "check_digit": s["gtin"][-1],
            "country_of_origin": world.PLANT[s["plant"]]["country"], "created_timestamp": created,
            "data_pool_publication_date": s["launch"] - datetime.timedelta(days=21), "data_pool_published": True,
            "ean_value": D(s["gtin"]), "gtin_value": D(s["gtin"]), "upc_value": None, "edi_eligible": True,
            "gpc_brick_code": _GPC[s["subcat"]], "gs1_company_prefix": s["gtin"][:7], "gs1_member_org": "GS1 Sweden",
            "gs1_registration_reference": "GS1SE-%s" % s["gtin"], "gs1_registry_published": True,
            "gtin_format": "GTIN-13", "indicator_digit": "0", "inner_packs_per_case": 1, "is_consumer_unit": True,
            "is_orderable": True, "is_scannable": True, "is_variable_measure": False,
            "item_reference_number": s["gtin"][7:12],
            "net_content_uom": {"g": "GRM", "kg": "KGM", "ml": "MLT", "L": "LTR", "units": "H87"}[s["uom"]],
            "net_content_value": D(str(s["content"])), "packaging_level": "each", "plm_lifecycle_stage": "active",
            "product_category": cat_name, "product_description": s["full_name"], "registration_status": "active",
            "retirement_date": None, "source_system_key": "MDG-%s" % s["code"], "target_market_country": "SWE",
            "units_per_case": case_qty,
            "last_updated_timestamp": _ts(datetime.date(2025, 6, 2) + datetime.timedelta(days=(i * 3) % 400), 8),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country="SWE"))
    reg.rows[fqn] = rows


def _main_material(s):
    sub = s["subcat"]
    recipe = _RECIPE.get(sub)
    if not recipe:
        return None
    mat = recipe[0][0]
    if sub == "CRISPBREAD" and "GF" in s["code"]:
        mat = "Buckwheat flour"
    if sub == "SPARKLING":
        mat = "CO2 food grade"
    return mat


def _bom_components(s):
    """(material name, component_type, required quantity per 1 000 EA, uom)."""
    out = []
    net_kg = D(str(s["content"])) / 1000 if s["uom"] in ("g", "ml") else D(str(s["content"]))
    mat = _main_material(s)
    if mat:
        share = [r for r in _RECIPE[s["subcat"]] if r[0] == mat or (mat in ("Buckwheat flour",) and r[0] == "Whole rye flour")]
        pct = D(share[0][2]) / 100 if share else D("0.5")
        if s["subcat"] == "SPARKLING":
            pct = D("0.007")
        out.append((mat, "raw_material", (D(1000) * net_kg * pct).quantize(D("0.000001")),
                    reg_uom(mat)))
    mat_code, ctype, _, _, _, case_qty, _ = _pack(s)
    pack = [p for p in _PACK if p[0] == mat_code][0]
    out.append((pack[1], "packaging", D("1000.000000") if ctype not in ("shrink multipack",) else D(1000 * s["pack"]), "EA"))
    out.append(("Corrugated shipping case", "packaging", (D(1000) / max(1, case_qty)).quantize(D("0.000001")), "EA"))
    return out


def reg_uom(mat):
    r = [x for x in _RAW if x[1] == mat]
    return r[0][3] if r else "EA"


def _product_boms(reg):
    fqn = "product.product_bom"
    pool = reg.alloc(fqn, len(world.SKUS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    rows = []
    for i, s in enumerate(world.SKUS):
        ids[s["code"]] = pool[i]
        created = _ts(s["launch"] - datetime.timedelta(days=110 + i % 30), 10)
        comps = _bom_components(s)
        fixed = {
            "product_bom_id": pool[i], "formulation_id": reg.ctx["formulation_id"][s["code"]],
            "manufacturing_facility_id": reg.ctx["plant_id"][s["plant"]], "sku_id": reg.ctx["sku_id"][s["code"]],
            "alternative_bom": "01", "approved_date": (created + datetime.timedelta(days=14)).date(),
            "base_quantity": D("1000.000000"), "base_uom": "EA", "bom_category": "material",
            "bom_description": "Production BOM for %s" % s["full_name"], "bom_level": 1,
            "bom_number": "PB-%s" % s["code"], "bom_type": "production", "change_number": "ECN-%05d" % (2000 + i),
            "component_count": len(comps), "costing_relevance": "relevant", "created_timestamp": created,
            "deletion_flag": False, "effective_from": s["launch"] - datetime.timedelta(days=30), "effective_until": None,
            "gmp_compliant": True, "is_configurable": False, "is_phantom": False,
            "lot_size_from": D("1000.000"), "lot_size_to": D("400000.000"), "lot_size_uom": "EA",
            "material_number": "FG%06d" % (s["index"] + 1), "mrp_relevance": True,
            "notes": None, "plant_code": s["plant"], "plm_status": "active", "production_version": "0001",
            "reach_compliant": True, "regulatory_approval_status": "approved" if s["category"] == "PERSONAL_CARE" else "not_required",
            "rspo_certified": s["category"] == "PERSONAL_CARE", "source_system_bom_code": "SAPBOM-%06d" % (s["index"] + 1),
            "version": "1.0", "last_changed_timestamp": _ts(datetime.date(2025, 9, 15) + datetime.timedelta(days=(i * 4) % 300), 11),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=world.PLANT[s["plant"]]["country"]))
    reg.ctx["product_bom_id"] = ids
    reg.rows[fqn] = rows


def _bom_lines(reg):
    fqn = "product.bom_line"
    specs = []
    for s in world.SKUS:
        for n, comp in enumerate(_bom_components(s), start=1):
            specs.append((s, n, comp))
    pool = reg.alloc(fqn, len(specs))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    rows = []
    for i, (s, n, (mat, ctype, qty, uom)) in enumerate(specs):
        info = reg.ctx["material_info"][mat]
        created = _ts(s["launch"] - datetime.timedelta(days=105), 10)
        cost_eur = info["cost"] * qty / (D(1) if uom != "EA" else D(1))
        pc_raw = s["category"] == "PERSONAL_CARE" and ctype == "raw_material"
        inci = None
        if pc_raw:
            inci = [r[3] for r in _RECIPE[s["subcat"]] if r[0] == mat]
            inci = inci[0] if inci else None
        fixed = {
            "bom_line_id": pool[i], "manufacturing_facility_id": reg.ctx["plant_id"][s["plant"]],
            "material_id": reg.ctx["material_id"][mat], "product_bom_id": reg.ctx["product_bom_id"][s["code"]],
            "sku_id": reg.ctx["sku_id"][s["code"]], "supplier_id": reg.pick("procurement.supplier", rnd),
            "alternative_item_group": None, "alternative_priority": 1, "bom_item_category": "stock",
            "bulk_material_flag": ctype == "raw_material" and uom in ("KG", "L"), "change_number": "ECN-%05d" % (2000 + s["index"]),
            "co_product_flag": False, "component_cost_usd": (cost_eur * D("1.08")).quantize(D("0.0001")),
            "component_item_number": "%04d" % (10 * n), "component_type": ctype, "created_timestamp": created,
            "currency_code": "USD", "fixed_quantity_flag": False, "hazardous_material_flag": info.get("group") in
            ("GASES", "SOLVENTS") or mat in ("Sodium laureth sulfate", "Sodium fluoride"),
            "inci_name": inci, "is_alternative_item": False, "is_critical_component": n == 1,
            "issue_method": "backflush", "line_number": n, "line_status": "active",
            "minimum_order_quantity": D("1000.0000") if uom == "EA" else D("500.0000"), "operation_number": 10 * n,
            "phantom_item_flag": False, "recursive_bom_flag": False, "required_quantity": qty,
            "reach_registration_number": ("01-%010d-%02d-%04d" % (2119400000 + i * 41, 20 + i % 60, 2000 + i)
                                          if pc_raw and mat in _CAS else None),
            "source_system_code": "SAP_PLM", "lead_time_offset_days": 0 if ctype == "packaging" else -1,
            "scrap_percentage": D("1.5000") if ctype == "raw_material" else D("0.8000"),
            "storage_location": "RM01 Raw materials" if ctype == "raw_material" else "PK01 Packaging",
            "unit_of_measure": uom, "usage_probability_pct": D("100.0000"),
            "valid_from_date": s["launch"] - datetime.timedelta(days=30), "valid_to_date": None,
            "last_modified_timestamp": _ts(datetime.date(2025, 9, 15) + datetime.timedelta(days=(i * 3) % 300), 12),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=world.PLANT[s["plant"]]["country"]))
    reg.rows[fqn] = rows
