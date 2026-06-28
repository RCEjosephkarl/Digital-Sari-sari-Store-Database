"""The Filipino-brand product catalog.

This is the *domain heart* of the project. Every product is a real, recognizable
Philippine sari-sari brand, organized into the six product groups requested:

    Meal Ingredients · Beverages · Snacks · Small Household Items ·
    Processed Meat · Liquor

Each product row carries:
    name, category, unit, base_price, reorder_level, popularity

`base_price` is a present-day (≈2026) reference selling price in PHP (₱). The
synthesizer *deflates* it for earlier years (see synthesize.inflation_factor),
so a 2011 receipt is cheaper than a 2025 one — realistic price history for
later time-series analytics. `popularity` (1–10) biases how often an item is
sold, so the data has believable bestsellers and slow movers.
"""
from __future__ import annotations

from typing import NamedTuple

# --- Reference data -----------------------------------------------------------

CATEGORIES: list[tuple[str, str]] = [
    ("Meal Ingredients", "Rice, cooking oil, condiments, seasonings and pantry staples"),
    ("Beverages", "Soft drinks, juices, coffee, milk, water and energy drinks"),
    ("Snacks", "Chips, crackers, instant noodles, biscuits and candies"),
    ("Small Household Items", "Detergents, soaps, shampoo and everyday non-food essentials"),
    ("Processed Meat", "Canned and chilled corned beef, hotdogs, sausages and canned fish"),
    ("Liquor", "Beer, gin, rum, brandy, vodka and wine"),
]

UNITS: list[tuple[str, str]] = [
    ("pc", "Piece"),
    ("sachet", "Sachet"),
    ("bottle", "Bottle"),
    ("can", "Can"),
    ("pack", "Pack"),
    ("kg", "Kilogram"),
    ("pouch", "Pouch"),
    ("tetra", "Tetra Pack"),
]

# Typical sari-sari markup (selling price / cost) per category — margins are thin.
CATEGORY_MARKUP: dict[str, float] = {
    "Meal Ingredients": 1.15,
    "Beverages": 1.18,
    "Snacks": 1.22,
    "Small Household Items": 1.18,
    "Processed Meat": 1.15,
    "Liquor": 1.12,
}

# Real Philippine distributors / wholesalers the store would buy from.
SUPPLIER_NAMES: list[str] = [
    "San Miguel Corporation Dealer",
    "Coca-Cola FEMSA Route Agent",
    "Pepsi-Cola Products Philippines",
    "Universal Robina (URC) Distributor",
    "Nestlé Philippines Dealer",
    "Monde Nissin Distributor",
    "Del Monte Philippines Sales",
    "CDO-Foodsphere Dealer",
    "Purefoods-Hormel Area Dealer",
    "Century Pacific Food Sales",
    "NutriAsia Distributor",
    "Procter & Gamble Philippines Dealer",
    "Unilever Philippines Distributor",
    "Colgate-Palmolive Dealer",
    "Ginebra San Miguel Inc. Dealer",
    "Tanduay Distillers Agent",
    "Emperador Distillers Agent",
    "Liwayway (Oishi) Distributor",
    "Rebisco Sales Agent",
    "Republic Biscuit Corporation",
    "Suy Sing Commercial Corporation",
    "Divisoria Wholesale Center",
    "Aling Nena Wholesale Trading",
    "Puregold Reseller Account",
    "Metro Manila Wholesale Mart",
    "Asia Brewery Dealer",
    "Zesto Corporation Sales",
    "RFM Corporation Distributor",
    "Ludan General Merchandise",
    "JBC Food Corporation Dealer",
]


class Product(NamedTuple):
    name: str
    category: str
    unit: str
    base_price: float
    reorder_level: int
    popularity: int


# --- Products (≈190 SKUs across the six groups) -------------------------------
# (name, category, unit, base_price ₱, reorder_level, popularity 1-10)
_RAW_PRODUCTS: list[tuple[str, str, str, float, int, int]] = [
    # ---------------- Meal Ingredients ----------------
    ("Sinandomeng Rice", "Meal Ingredients", "kg", 52, 40, 10),
    ("Jasmine Rice", "Meal Ingredients", "kg", 56, 30, 7),
    ("Dinorado Rice", "Meal Ingredients", "kg", 60, 25, 6),
    ("Well-Milled Rice", "Meal Ingredients", "kg", 45, 40, 8),
    ("Baguio Oil Cooking Oil 1L", "Meal Ingredients", "bottle", 95, 12, 7),
    ("Golden Fiesta Palm Oil 1L", "Meal Ingredients", "bottle", 92, 12, 7),
    ("Minola Coconut Oil 1L", "Meal Ingredients", "bottle", 98, 8, 5),
    ("Datu Puti Soy Sauce 385ml", "Meal Ingredients", "bottle", 28, 15, 9),
    ("Silver Swan Soy Sauce 385ml", "Meal Ingredients", "bottle", 27, 12, 8),
    ("Marca Piña Soy Sauce 385ml", "Meal Ingredients", "bottle", 26, 8, 5),
    ("Datu Puti Vinegar 385ml", "Meal Ingredients", "bottle", 25, 12, 8),
    ("Silver Swan Vinegar 385ml", "Meal Ingredients", "bottle", 24, 10, 7),
    ("Rufina Patis 350ml", "Meal Ingredients", "bottle", 30, 10, 6),
    ("Lorins Patis 350ml", "Meal Ingredients", "bottle", 28, 6, 4),
    ("UFC Banana Catsup 320g", "Meal Ingredients", "bottle", 38, 12, 8),
    ("Papa Banana Catsup 320g", "Meal Ingredients", "bottle", 36, 8, 6),
    ("Del Monte Tomato Sauce 250g", "Meal Ingredients", "pouch", 22, 10, 7),
    ("UFC Tomato Sauce 250g", "Meal Ingredients", "pouch", 21, 8, 6),
    ("Hunt's Tomato Sauce 250g", "Meal Ingredients", "pouch", 23, 6, 5),
    ("Knorr Chicken Cube", "Meal Ingredients", "pc", 6, 20, 8),
    ("Maggi Magic Sarap 8g", "Meal Ingredients", "sachet", 6, 30, 10),
    ("Ajinomoto Umami Seasoning 11g", "Meal Ingredients", "sachet", 5, 30, 9),
    ("Knorr Sinigang sa Sampaloc Mix 22g", "Meal Ingredients", "sachet", 12, 20, 9),
    ("Mama Sita's Sinigang Mix 50g", "Meal Ingredients", "pack", 18, 10, 7),
    ("Mama Sita's Kare-Kare Mix 57g", "Meal Ingredients", "pack", 28, 6, 5),
    ("White Refined Sugar", "Meal Ingredients", "kg", 70, 15, 8),
    ("Brown Sugar", "Meal Ingredients", "kg", 65, 10, 6),
    ("Fidel Iodized Salt 1kg", "Meal Ingredients", "pack", 22, 10, 7),
    ("Maya All-Purpose Flour 1kg", "Meal Ingredients", "pack", 65, 6, 5),
    ("Star Margarine 100g", "Meal Ingredients", "pc", 22, 10, 7),
    ("Dari Creme Margarine 100g", "Meal Ingredients", "pc", 20, 8, 5),
    # ---------------- Beverages ----------------
    ("Coca-Cola Mismo 295ml", "Beverages", "bottle", 15, 24, 10),
    ("Coke 1.5L", "Beverages", "bottle", 75, 12, 8),
    ("Pepsi 295ml", "Beverages", "bottle", 14, 18, 8),
    ("Royal Tru-Orange 295ml", "Beverages", "bottle", 14, 15, 7),
    ("Sprite Mismo 295ml", "Beverages", "bottle", 15, 18, 8),
    ("Mountain Dew 295ml", "Beverages", "bottle", 14, 15, 7),
    ("Mirinda Orange 295ml", "Beverages", "bottle", 13, 10, 5),
    ("7-Up 295ml", "Beverages", "bottle", 14, 10, 5),
    ("RC Cola 295ml", "Beverages", "bottle", 12, 10, 5),
    ("Sarsi 295ml", "Beverages", "bottle", 13, 8, 4),
    ("Cobra Energy Drink 240ml", "Beverages", "bottle", 25, 12, 7),
    ("Sting Energy Drink 240ml", "Beverages", "bottle", 22, 12, 7),
    ("Red Bull 250ml", "Beverages", "can", 55, 6, 4),
    ("Extra Joss Sachet", "Beverages", "sachet", 9, 20, 6),
    ("C2 Green Tea Apple 500ml", "Beverages", "bottle", 30, 12, 7),
    ("Zesto Orange 200ml", "Beverages", "tetra", 9, 20, 7),
    ("Tang Orange 25g", "Beverages", "sachet", 8, 24, 8),
    ("Eight O'Clock Juice 200ml", "Beverages", "tetra", 9, 12, 5),
    ("Del Monte Pineapple Juice 240ml", "Beverages", "can", 28, 10, 5),
    ("Nescafé Original 3-in-1", "Beverages", "sachet", 8, 40, 10),
    ("Nescafé Classic Stick", "Beverages", "sachet", 7, 30, 8),
    ("Kopiko Black 3-in-1", "Beverages", "sachet", 8, 30, 9),
    ("Great Taste White 3-in-1", "Beverages", "sachet", 8, 30, 9),
    ("San Mig Coffee 3-in-1", "Beverages", "sachet", 7, 24, 7),
    ("Milo 24g Sachet", "Beverages", "sachet", 12, 30, 9),
    ("Bear Brand Powdered Milk 33g", "Beverages", "sachet", 13, 30, 9),
    ("Alaska Evaporada 154ml", "Beverages", "can", 24, 15, 7),
    ("Alaska Condensada 168ml", "Beverages", "can", 35, 12, 6),
    ("Nido Fortified 80g", "Beverages", "pack", 45, 8, 5),
    ("Wilkins Distilled Water 500ml", "Beverages", "bottle", 20, 15, 7),
    ("Nature's Spring Water 500ml", "Beverages", "bottle", 15, 15, 7),
    ("Absolute Distilled Water 350ml", "Beverages", "bottle", 12, 12, 6),
    # ---------------- Snacks ----------------
    ("Lucky Me Pancit Canton Original 60g", "Snacks", "pack", 15, 30, 10),
    ("Lucky Me Pancit Canton Chilimansi 60g", "Snacks", "pack", 15, 24, 8),
    ("Lucky Me Instant Mami Beef 55g", "Snacks", "pack", 13, 24, 8),
    ("Nissin Cup Noodles Seafood 60g", "Snacks", "pack", 32, 12, 6),
    ("Payless Xtra Big Noodles 70g", "Snacks", "pack", 18, 12, 6),
    ("Piattos Cheese 40g", "Snacks", "pack", 16, 18, 9),
    ("Nova Multigrain 40g", "Snacks", "pack", 16, 12, 7),
    ("Chippy Barbecue 110g", "Snacks", "pack", 28, 12, 7),
    ("V-Cut Spicy Barbecue 60g", "Snacks", "pack", 16, 12, 7),
    ("Clover Chips Cheese 85g", "Snacks", "pack", 14, 10, 6),
    ("Mr. Chips Nacho Cheese 50g", "Snacks", "pack", 16, 10, 6),
    ("Roller Coaster Potato Rings 60g", "Snacks", "pack", 16, 10, 6),
    ("Oishi Prawn Crackers 60g", "Snacks", "pack", 16, 14, 8),
    ("Oishi Pillows Chocolate 38g", "Snacks", "pack", 16, 10, 6),
    ("Boy Bawang Cornick Garlic 100g", "Snacks", "pack", 22, 14, 8),
    ("Tortillos Cheese 40g", "Snacks", "pack", 16, 8, 5),
    ("Cheetos Cheese 50g", "Snacks", "pack", 16, 8, 5),
    ("Skyflakes Crackers 25g", "Snacks", "pack", 9, 24, 9),
    ("Fita Crackers 30g", "Snacks", "pack", 9, 18, 8),
    ("Rebisco Crackers 33g", "Snacks", "pack", 8, 24, 8),
    ("Hansel Sandwich 31g", "Snacks", "pack", 8, 18, 7),
    ("Magic Flakes Crackers 28g", "Snacks", "pack", 9, 18, 7),
    ("Cream-O Vanilla 24g", "Snacks", "pack", 8, 18, 8),
    ("Presto Creams Chocolate 28g", "Snacks", "pack", 8, 12, 6),
    ("Cloud 9 Chocolate Bar 30g", "Snacks", "pc", 9, 18, 8),
    ("Curly Tops Chocolate 18g", "Snacks", "pc", 8, 14, 7),
    ("Goya Chocolate Bar 40g", "Snacks", "pc", 12, 10, 6),
    ("Hany Choco Bar 12g", "Snacks", "pc", 6, 14, 7),
    ("Mentos Mint Roll", "Snacks", "pc", 12, 10, 6),
    ("Maxx Hard Candy", "Snacks", "pc", 1, 40, 8),
    ("Storck Assorted Candy", "Snacks", "pc", 2, 30, 6),
    ("Halls Menthol Candy", "Snacks", "pc", 2, 30, 6),
    # ---------------- Small Household Items ----------------
    ("Tide Powder 66g Sachet", "Small Household Items", "sachet", 12, 24, 9),
    ("Ariel Powder 66g Sachet", "Small Household Items", "sachet", 13, 24, 9),
    ("Surf Powder 70g Sachet", "Small Household Items", "sachet", 9, 30, 9),
    ("Champion Powder 70g Sachet", "Small Household Items", "sachet", 8, 24, 7),
    ("Pride Powder 65g Sachet", "Small Household Items", "sachet", 8, 18, 6),
    ("Wings Powder 100g Sachet", "Small Household Items", "sachet", 9, 18, 7),
    ("Joy Dishwashing Liquid 45ml Sachet", "Small Household Items", "sachet", 12, 24, 8),
    ("Smart Dishwashing Paste 200g", "Small Household Items", "pc", 25, 10, 6),
    ("Axion Dishwashing Paste 190g", "Small Household Items", "pc", 24, 8, 5),
    ("Downy Fabric Conditioner 27ml Sachet", "Small Household Items", "sachet", 8, 24, 8),
    ("Surf Fabric Conditioner 26ml Sachet", "Small Household Items", "sachet", 7, 18, 6),
    ("Safeguard Soap 130g", "Small Household Items", "pc", 38, 12, 9),
    ("Bioderm Germicidal Soap 90g", "Small Household Items", "pc", 30, 8, 6),
    ("Silka Papaya Soap 135g", "Small Household Items", "pc", 42, 8, 6),
    ("Palmolive Soap 115g", "Small Household Items", "pc", 34, 8, 6),
    ("Dove Beauty Bar 100g", "Small Household Items", "pc", 55, 6, 5),
    ("Sunsilk Shampoo 12ml Sachet", "Small Household Items", "sachet", 7, 30, 9),
    ("Palmolive Shampoo 12ml Sachet", "Small Household Items", "sachet", 7, 30, 9),
    ("Head & Shoulders Shampoo 12ml Sachet", "Small Household Items", "sachet", 9, 24, 8),
    ("Clear Shampoo 12ml Sachet", "Small Household Items", "sachet", 9, 18, 6),
    ("Cream Silk Conditioner 12ml Sachet", "Small Household Items", "sachet", 8, 24, 8),
    ("Colgate Toothpaste 25g", "Small Household Items", "pc", 22, 12, 8),
    ("Close-Up Toothpaste 25g", "Small Household Items", "pc", 22, 10, 7),
    ("Hapee Toothpaste 25g", "Small Household Items", "pc", 15, 10, 6),
    ("Zonrox Bleach 250ml", "Small Household Items", "bottle", 22, 10, 7),
    ("Baygon Insect Spray 150ml", "Small Household Items", "can", 95, 5, 4),
    ("Off Lotion Sachet", "Small Household Items", "sachet", 10, 12, 5),
    ("Eveready AA Battery", "Small Household Items", "pc", 18, 10, 6),
    ("Femme Facial Tissue 50s", "Small Household Items", "pack", 18, 8, 6),
    ("Match Box", "Small Household Items", "pc", 3, 20, 6),
    ("Household Candle", "Small Household Items", "pc", 8, 12, 6),
    # ---------------- Processed Meat ----------------
    ("Argentina Corned Beef 150g", "Processed Meat", "can", 38, 18, 10),
    ("Star Corned Beef 150g", "Processed Meat", "can", 35, 12, 7),
    ("Purefoods Corned Beef 150g", "Processed Meat", "can", 40, 12, 7),
    ("Delimondo Corned Beef 180g", "Processed Meat", "can", 145, 4, 3),
    ("CDO Karne Norte 150g", "Processed Meat", "can", 33, 12, 7),
    ("555 Corned Beef 150g", "Processed Meat", "can", 34, 10, 6),
    ("Argentina Meat Loaf 150g", "Processed Meat", "can", 25, 15, 8),
    ("555 Meat Loaf 150g", "Processed Meat", "can", 24, 15, 8),
    ("CDO Meat Loaf 150g", "Processed Meat", "can", 23, 10, 6),
    ("Maling Luncheon Meat 397g", "Processed Meat", "can", 95, 6, 5),
    ("CDO Liver Spread 85g", "Processed Meat", "can", 22, 10, 6),
    ("Spam Luncheon Meat 340g", "Processed Meat", "can", 165, 4, 3),
    ("Argentina Vienna Sausage 130g", "Processed Meat", "can", 28, 15, 8),
    ("Purefoods Vienna Sausage 130g", "Processed Meat", "can", 30, 12, 7),
    ("CDO Vienna Sausage 130g", "Processed Meat", "can", 27, 10, 6),
    ("Purefoods Tender Juicy Hotdog 250g", "Processed Meat", "pack", 78, 12, 8),
    ("CDO Bibbo Hotdog 250g", "Processed Meat", "pack", 70, 10, 7),
    ("Beefies Hotdog 250g", "Processed Meat", "pack", 65, 8, 6),
    ("Virginia Cocktail Hotdog 250g", "Processed Meat", "pack", 72, 8, 6),
    ("Winner Hotdog 1kg", "Processed Meat", "pack", 180, 4, 4),
    ("Purefoods Pork Tocino 250g", "Processed Meat", "pack", 85, 6, 5),
    ("CDO Pork Longganisa 250g", "Processed Meat", "pack", 80, 6, 5),
    ("Purefoods Chicken Nuggets 200g", "Processed Meat", "pack", 95, 5, 4),
    ("555 Sardines Red 155g", "Processed Meat", "can", 22, 18, 9),
    ("555 Sardines Green 155g", "Processed Meat", "can", 22, 15, 8),
    ("Mega Sardines 155g", "Processed Meat", "can", 25, 15, 8),
    ("Ligo Sardines 155g", "Processed Meat", "can", 23, 12, 7),
    ("Young's Town Sardines 155g", "Processed Meat", "can", 21, 10, 6),
    ("Century Tuna Flakes in Oil 180g", "Processed Meat", "can", 42, 10, 7),
    ("San Marino Corned Tuna 180g", "Processed Meat", "can", 38, 8, 6),
    ("Argentina Beef Loaf 150g", "Processed Meat", "can", 26, 10, 6),
    # ---------------- Liquor ----------------
    ("San Miguel Pale Pilsen 330ml", "Liquor", "bottle", 55, 24, 10),
    ("Red Horse Beer 500ml", "Liquor", "bottle", 75, 24, 10),
    ("San Mig Light 330ml", "Liquor", "bottle", 58, 18, 8),
    ("San Miguel Apple Flavored Beer 330ml", "Liquor", "bottle", 60, 10, 6),
    ("San Miguel Pilsen Litro 1L", "Liquor", "bottle", 110, 10, 6),
    ("Red Horse Beer Litro 1L", "Liquor", "bottle", 130, 12, 7),
    ("Ginebra San Miguel GSM Blue 350ml", "Liquor", "bottle", 75, 15, 8),
    ("Ginebra San Miguel Bilog 350ml", "Liquor", "bottle", 70, 15, 8),
    ("Gilbey's Gin 350ml", "Liquor", "bottle", 95, 6, 5),
    ("Tanduay Select Rum 750ml", "Liquor", "bottle", 145, 10, 7),
    ("Tanduay Five Years Rum 750ml", "Liquor", "bottle", 165, 6, 5),
    ("Tanduay Ice Lychee 330ml", "Liquor", "bottle", 45, 10, 6),
    ("Emperador Brandy 750ml", "Liquor", "bottle", 170, 10, 7),
    ("Emperador Light 750ml", "Liquor", "bottle", 160, 8, 6),
    ("Fundador Brandy 750ml", "Liquor", "bottle", 230, 4, 3),
    ("Generoso Brandy 750ml", "Liquor", "bottle", 175, 5, 4),
    ("Antonov Vodka 700ml", "Liquor", "bottle", 140, 5, 4),
    ("Cossacks Vodka 700ml", "Liquor", "bottle", 135, 4, 3),
    ("Jinro Chamisul Soju 360ml", "Liquor", "bottle", 95, 6, 5),
    ("Novellino Red Wine 750ml", "Liquor", "bottle", 220, 4, 3),
    ("Carlo Rossi Red 750ml", "Liquor", "bottle", 320, 3, 2),
    ("GSM Flavored Gin Pomelo 350ml", "Liquor", "bottle", 80, 8, 5),
    ("Tanduay Cocktail 700ml", "Liquor", "bottle", 120, 5, 4),
    ("The Bar Vodka 700ml", "Liquor", "bottle", 150, 4, 3),
    ("Empi Light Brandy 375ml", "Liquor", "bottle", 90, 6, 5),
    ("San Miguel Flavored Lemon 330ml", "Liquor", "bottle", 60, 6, 4),
    ("Colt 45 High Gravity Beer 330ml", "Liquor", "bottle", 60, 8, 5),
    ("Beer na Beer 330ml", "Liquor", "bottle", 45, 6, 4),
    ("Smirnoff Mule 330ml", "Liquor", "bottle", 70, 6, 4),
    ("Jinro Grapefruit Soju 360ml", "Liquor", "bottle", 98, 5, 4),
]

PRODUCTS: list[Product] = [Product(*row) for row in _RAW_PRODUCTS]


def product_count() -> int:
    return len(PRODUCTS)


def cost_for(category: str, price: float) -> float:
    """Wholesale cost implied by a category's typical markup."""
    return round(price / CATEGORY_MARKUP.get(category, 1.18), 2)
