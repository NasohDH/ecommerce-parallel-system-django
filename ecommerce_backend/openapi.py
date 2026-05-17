OPENAPI_SCHEMA = {
    "openapi": "3.1.0",
    "info": {
        "title": "E-commerce Backend",
        "version": "1.0.0",
        "description": "Django REST Framework API migrated from the original FastAPI ecommerce backend.",
    },
    "paths": {
        "/": {
            "get": {
                "summary": "API health message",
                "responses": {
                    "200": {
                        "description": "API is running",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/RootResponse"}
                            }
                        },
                    }
                },
            }
        },
        "/users": {
            "get": {
                "summary": "List users",
                "parameters": [
                    {"$ref": "#/components/parameters/Skip"},
                    {"$ref": "#/components/parameters/Limit"},
                ],
                "responses": {
                    "200": {
                        "description": "Users",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/User"},
                                }
                            }
                        },
                    }
                },
            }
        },
        "/users/{user_id}": {
            "get": {
                "summary": "Get user",
                "parameters": [{"$ref": "#/components/parameters/UserId"}],
                "responses": {
                    "200": {
                        "description": "User",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        },
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/products": {
            "get": {
                "summary": "List products",
                "parameters": [
                    {"$ref": "#/components/parameters/Skip"},
                    {"$ref": "#/components/parameters/Limit"},
                ],
                "responses": {
                    "200": {
                        "description": "Products",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Product"},
                                }
                            }
                        },
                    }
                },
            }
        },
        "/products/{product_id}": {
            "get": {
                "summary": "Get product",
                "parameters": [{"$ref": "#/components/parameters/ProductId"}],
                "responses": {
                    "200": {
                        "description": "Product",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Product"}
                            }
                        },
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/cart/{user_id}": {
            "get": {
                "summary": "Get user cart",
                "parameters": [{"$ref": "#/components/parameters/UserId"}],
                "responses": {
                    "200": {
                        "description": "Cart",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Cart"}
                            }
                        },
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/cart/items": {
            "post": {
                "summary": "Add item to cart",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/AddCartItem"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Updated cart",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Cart"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/cart/items/{cart_item_id}": {
            "put": {
                "summary": "Update cart item quantity",
                "parameters": [{"$ref": "#/components/parameters/CartItemId"}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/UpdateCartItem"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Updated cart item",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CartItem"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            },
            "delete": {
                "summary": "Delete cart item",
                "parameters": [{"$ref": "#/components/parameters/CartItemId"}],
                "responses": {
                    "200": {
                        "description": "Deleted",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Message"}
                            }
                        },
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            },
        },
        "/orders": {
            "get": {
                "summary": "List orders",
                "parameters": [
                    {
                        "name": "user_id",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer"},
                    },
                    {"$ref": "#/components/parameters/Skip"},
                    {"$ref": "#/components/parameters/Limit"},
                ],
                "responses": {
                    "200": {
                        "description": "Orders",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Order"},
                                }
                            }
                        },
                    }
                },
            }
        },
        "/orders/user/{user_id}": {
            "get": {
                "summary": "List orders for user",
                "parameters": [
                    {"$ref": "#/components/parameters/UserId"},
                    {"$ref": "#/components/parameters/Skip"},
                    {"$ref": "#/components/parameters/Limit"},
                ],
                "responses": {
                    "200": {
                        "description": "Orders",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Order"},
                                }
                            }
                        },
                    }
                },
            }
        },
        "/orders/{order_id}": {
            "get": {
                "summary": "Get order",
                "parameters": [{"$ref": "#/components/parameters/OrderId"}],
                "responses": {
                    "200": {
                        "description": "Order",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Order"}
                            }
                        },
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/orders/checkout": {
            "post": {
                "summary": "Checkout cart",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Checkout"}
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Created order",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Order"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "503": {"$ref": "#/components/responses/ServiceUnavailable"},
                },
            }
        },
    },
    "components": {
        "parameters": {
            "Skip": {
                "name": "skip",
                "in": "query",
                "required": False,
                "schema": {"type": "integer", "default": 0, "minimum": 0},
            },
            "Limit": {
                "name": "limit",
                "in": "query",
                "required": False,
                "schema": {
                    "type": "integer",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 500,
                },
            },
            "UserId": {
                "name": "user_id",
                "in": "path",
                "required": True,
                "schema": {"type": "integer"},
            },
            "ProductId": {
                "name": "product_id",
                "in": "path",
                "required": True,
                "schema": {"type": "integer"},
            },
            "CartItemId": {
                "name": "cart_item_id",
                "in": "path",
                "required": True,
                "schema": {"type": "integer"},
            },
            "OrderId": {
                "name": "order_id",
                "in": "path",
                "required": True,
                "schema": {"type": "integer"},
            },
        },
        "responses": {
            "BadRequest": {
                "description": "Bad request",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"}
                    }
                },
            },
            "NotFound": {
                "description": "Not found",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"}
                    }
                },
            },
            "ServiceUnavailable": {
                "description": "Service unavailable",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"}
                    }
                },
            },
        },
        "schemas": {
            "RootResponse": {
                "type": "object",
                "required": ["message"],
                "properties": {"message": {"type": "string"}},
            },
            "Message": {
                "type": "object",
                "required": ["message"],
                "properties": {"message": {"type": "string"}},
            },
            "Error": {
                "type": "object",
                "required": ["detail"],
                "properties": {"detail": {"type": "string"}},
            },
            "User": {
                "type": "object",
                "required": ["id", "email", "username", "balance", "created_at"],
                "properties": {
                    "id": {"type": "integer"},
                    "email": {"type": "string", "format": "email"},
                    "username": {"type": "string"},
                    "balance": {"type": "string", "format": "decimal"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "Product": {
                "type": "object",
                "required": ["id", "name", "price", "stock_quantity", "created_at"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "description": {"type": ["string", "null"]},
                    "price": {"type": "number", "format": "float"},
                    "stock_quantity": {"type": "integer"},
                    "image_url": {"type": ["string", "null"]},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "AddCartItem": {
                "type": "object",
                "required": ["user_id", "product_id", "quantity"],
                "properties": {
                    "user_id": {"type": "integer"},
                    "product_id": {"type": "integer"},
                    "quantity": {"type": "integer"},
                },
            },
            "UpdateCartItem": {
                "type": "object",
                "required": ["quantity"],
                "properties": {"quantity": {"type": "integer"}},
            },
            "CartItem": {
                "type": "object",
                "required": [
                    "id",
                    "cart_id",
                    "product_id",
                    "quantity",
                    "created_at",
                    "product",
                ],
                "properties": {
                    "id": {"type": "integer"},
                    "cart_id": {"type": "integer"},
                    "product_id": {"type": "integer"},
                    "quantity": {"type": "integer"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "product": {"$ref": "#/components/schemas/Product"},
                },
            },
            "Cart": {
                "type": "object",
                "required": ["id", "user_id", "created_at", "items"],
                "properties": {
                    "id": {"type": ["integer", "null"]},
                    "user_id": {"type": "integer"},
                    "created_at": {"type": ["string", "null"], "format": "date-time"},
                    "items": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/CartItem"},
                    },
                },
            },
            "Checkout": {
                "type": "object",
                "required": ["user_id"],
                "properties": {"user_id": {"type": "integer"}},
            },
            "OrderItem": {
                "type": "object",
                "required": [
                    "id",
                    "product_id",
                    "quantity",
                    "unit_price",
                    "subtotal",
                    "created_at",
                ],
                "properties": {
                    "id": {"type": "integer"},
                    "product_id": {"type": "integer"},
                    "quantity": {"type": "integer"},
                    "unit_price": {"type": "number", "format": "float"},
                    "subtotal": {"type": "number", "format": "float"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "Order": {
                "type": "object",
                "required": [
                    "id",
                    "user_id",
                    "total_price",
                    "status",
                    "created_at",
                    "items",
                ],
                "properties": {
                    "id": {"type": "integer"},
                    "user_id": {"type": "integer"},
                    "total_price": {"type": "number", "format": "float"},
                    "status": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "items": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/OrderItem"},
                    },
                },
            },
        },
    },
}
