"""What the simulated Salesforce already holds before the demo starts: the customers (Accounts) and
what they can buy (Product2 with its standard price). Written once, on first read; from then on it
is Salesforce's own data. Fictional companies and products."""

ACCOUNTS = [
    {"id": "ACME", "AccountNumber": "ACME", "Name": "ACME Corporation", "Industry": "Manufacturing",
     "ShippingStreet": "Rue de la Loi 16", "ShippingPostalCode": "1000", "ShippingCity": "Brussels", "ShippingCountryCode": "BE",
     "CurrencyIsoCode": "EUR"},
    {"id": "GLOBEX", "AccountNumber": "GLOBEX", "Name": "Globex Corporation", "Industry": "Energy",
     "ShippingStreet": "Meir 50", "ShippingPostalCode": "2000", "ShippingCity": "Antwerp", "ShippingCountryCode": "BE",
     "CurrencyIsoCode": "EUR"},
    {"id": "INITECH", "AccountNumber": "INITECH", "Name": "Initech", "Industry": "Technology",
     "ShippingStreet": "Korenmarkt 1", "ShippingPostalCode": "9000", "ShippingCity": "Ghent", "ShippingCountryCode": "BE",
     "CurrencyIsoCode": "EUR"},
    {"id": "NORDFJORD", "AccountNumber": "NORDFJORD", "Name": "Nordfjord Supplies AB", "Industry": "Wholesale",
     "ShippingStreet": "Sveavägen 44", "ShippingPostalCode": "111 34", "ShippingCity": "Stockholm", "ShippingCountryCode": "SE",
     "CurrencyIsoCode": "EUR"},
]

PRODUCTS = [
    {"id": "SKU-1042", "ProductCode": "SKU-1042", "Name": "Hydraulic Press HP-1042", "Description": "40-tonne hydraulic workshop press.",
     "Family": "Machinery", "StandardPrice": 7000.0, "CurrencyIsoCode": "EUR", "IsActive": True},
    {"id": "SKU-2001", "ProductCode": "SKU-2001", "Name": "Conveyor Belt Module CB-2001", "Description": "2-metre modular belt conveyor.",
     "Family": "Material Handling", "StandardPrice": 1250.0, "CurrencyIsoCode": "EUR", "IsActive": True},
    {"id": "SKU-3310", "ProductCode": "SKU-3310", "Name": "Pallet Racking Bay PR-3310", "Description": "Three-level bay for 9 euro pallets.",
     "Family": "Storage", "StandardPrice": 480.0, "CurrencyIsoCode": "EUR", "IsActive": True},
    {"id": "SKU-0420", "ProductCode": "SKU-0420", "Name": "Safety Light Curtain SL-0420", "Description": "Type 4 light curtain, 1.2 m.",
     "Family": "Safety", "StandardPrice": 895.0, "CurrencyIsoCode": "EUR", "IsActive": True},
    {"id": "SKU-7788", "ProductCode": "SKU-7788", "Name": "Forklift Battery FB-7788", "Description": "48 V lithium-ion traction battery.",
     "Family": "Material Handling", "StandardPrice": 3900.0, "CurrencyIsoCode": "EUR", "IsActive": True},
    {"id": "SKU-5150", "ProductCode": "SKU-5150", "Name": "Industrial Workbench WB-5150", "Description": "Steel workbench with drawers.",
     "Family": "Workshop", "StandardPrice": 640.0, "CurrencyIsoCode": "EUR", "IsActive": True},
]
