from sanic_openapi import doc


class ItemPostRequest:
    brand = doc.String()
    name = doc.String(required=True)
    item_size = doc.Float(required=True)
    unit = doc.String(required=True)
    count = doc.Float(required=True)
    category = doc.String()
    subcategory = doc.String()
    expiration_date = doc.Date()
