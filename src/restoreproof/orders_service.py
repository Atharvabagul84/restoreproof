"""Authentication and input rules for a bounded synthetic orders service."""
import secrets
from uuid import uuid4

from .orders_repository import canonical_uuid, quantity_value


class OrdersError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class OrdersService:
    def __init__(self, repository, token_tenants):
        self.repository = repository
        self.token_tenants = dict(token_tenants)

    def _tenant(self, authorization):
        if isinstance(authorization, str) and authorization.isascii() and len(authorization) <= 256:
            for token, tenant in self.token_tenants.items():
                if secrets.compare_digest(authorization, "Bearer " + token):
                    return tenant
        raise OrdersError(401, "Authentication required.")

    def get(self, authorization, order_id):
        tenant = self._tenant(authorization)
        try:
            canonical_uuid(order_id)
        except ValueError:
            raise OrdersError(400, "Invalid order identifier.") from None
        result = self.repository.get(tenant, order_id)
        if result is None:
            raise OrdersError(404, "Order not found.")
        return result

    def create(self, authorization, payload):
        tenant = self._tenant(authorization)
        if not isinstance(payload, dict) or set(payload) != {"quantity"}:
            raise OrdersError(400, "Provide only quantity.")
        try:
            quantity = quantity_value(payload["quantity"])
        except ValueError:
            raise OrdersError(400, "Quantity must be an integer between 1 and 10000.") from None
        return self.repository.create(tenant, str(uuid4()), quantity)
