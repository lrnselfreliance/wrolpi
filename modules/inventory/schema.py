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


class ItemPutRequest:
    id = doc.Integer()  # Ignored in favor of URL
    brand = doc.String()
    name = doc.String(required=True)
    item_size = doc.Float(required=True)
    unit = doc.String(required=True)
    count = doc.Float(required=True)
    serving = doc.Float()
    category = doc.String()
    subcategory = doc.String()
    expiration_date = doc.Date()
    purchase_date = doc.Date()
    created_at = doc.DateTime()
    deleted_at = doc.DateTime()
    inventory_id = doc.Integer(required=True)


class InventoryPostRequest:
    name = doc.String(required=True)


class InventoryPutRequest:
    name = doc.String(required=True)
