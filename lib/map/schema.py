from marshmallow import Schema, fields


class PBFPost(Schema):
    pbf = fields.Str()


pbf_post_schema = PBFPost()
