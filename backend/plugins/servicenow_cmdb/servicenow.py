"""
ServiceNow CMDB Client — Queries the ServiceNow Table API for Configuration Items.

Uses basic authentication and the Table API:
  GET /api/now/table/{table}?sysparm_query=...

Returns matching CIs with a direct link to the record in ServiceNow.
"""

import traceback
from typing import Any

import httpx


class ServiceNowClient:
    """Handles ServiceNow Table API queries."""

    def __init__(self, instance_url: str, username: str, password: str, table: str = "cmdb_ci"):
        # Normalise — strip trailing slash
        self.instance_url = instance_url.rstrip("/")
        self.username = username
        self.password = password
        self.table = table

    def _build_link(self, sys_id: str) -> str:
        """Build a direct link to a CI record in ServiceNow."""
        return f"{self.instance_url}/nav_to.do?uri={self.table}.do?sys_id={sys_id}"

    async def lookup(self, query: str, limit: int = 10) -> dict[str, Any]:
        """
        Search the CMDB table for CIs matching the query.

        Searches across name, ip_address, and fqdn fields.
        """
        # Build a ServiceNow encoded query:
        # nameLIKE<query> OR ip_addressLIKE<query> OR fqdnLIKE<query>
        encoded_query = (
            f"nameLIKE{query}"
            f"^ORip_addressLIKE{query}"
            f"^ORfqdnLIKE{query}"
            f"^ORhost_nameLIKE{query}"
        )

        fields = "sys_id,name,ip_address,fqdn,host_name,sys_class_name,operational_status,os,os_version,category,subcategory,asset_tag,serial_number,company,department,location,sys_updated_on"

        try:
            async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
                resp = await client.get(
                    f"{self.instance_url}/api/now/table/{self.table}",
                    params={
                        "sysparm_query": encoded_query,
                        "sysparm_fields": fields,
                        "sysparm_limit": str(limit),
                        "sysparm_display_value": "true",
                    },
                    auth=(self.username, self.password),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )

                if resp.status_code == 401:
                    return {"error": "Authentication failed. Check your ServiceNow credentials.", "results": []}
                if resp.status_code == 403:
                    return {"error": "Access denied. Ensure the account has read access to the CMDB table.", "results": []}
                if resp.status_code != 200:
                    return {"error": f"ServiceNow API returned HTTP {resp.status_code}", "results": []}

                data = resp.json()
                records = data.get("result", [])

                results = []
                for record in records:
                    sys_id = record.get("sys_id", "")
                    results.append({
                        "sys_id": sys_id,
                        "name": record.get("name", ""),
                        "ip_address": record.get("ip_address", ""),
                        "fqdn": record.get("fqdn", ""),
                        "host_name": record.get("host_name", ""),
                        "class": record.get("sys_class_name", ""),
                        "status": record.get("operational_status", ""),
                        "os": record.get("os", ""),
                        "os_version": record.get("os_version", ""),
                        "category": record.get("category", ""),
                        "subcategory": record.get("subcategory", ""),
                        "asset_tag": record.get("asset_tag", ""),
                        "serial_number": record.get("serial_number", ""),
                        "company": record.get("company", ""),
                        "department": record.get("department", ""),
                        "location": record.get("location", ""),
                        "updated_on": record.get("sys_updated_on", ""),
                        "link": self._build_link(sys_id),
                    })

                return {
                    "query": query,
                    "table": self.table,
                    "count": len(results),
                    "results": results,
                }

        except httpx.ConnectError:
            return {"error": f"Could not connect to {self.instance_url}. Check the instance URL.", "results": []}
        except httpx.TimeoutException:
            return {"error": "Request to ServiceNow timed out.", "results": []}
        except Exception as e:
            print(f"[ServiceNow] API error: {e}")
            traceback.print_exc()
            return {"error": f"Unexpected error: {str(e)}", "results": []}
