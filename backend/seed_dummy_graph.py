import asyncio
from neo4j import AsyncGraphDatabase
from backend.services.graph_builder import CrimeGraphBuilder
from backend.models.graph import EntityNode, Relationship

from backend.core.config import get_settings

async def seed_dummy_graph():
    print("Connecting to Neo4j Graph Database...")
    settings = get_settings()
    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    builder = CrimeGraphBuilder(driver)

    print("Creating Target: John Doe...")
    john = EntityNode(node_type="Person", properties={"name": "John Doe", "alias": "GhostHacker99"})
    john_id = await builder.create_entity(john)

    print("Creating Linked Entities...")
    email = EntityNode(node_type="DigitalIdentity", properties={"type": "Email", "email": "ghosthacker99@protonmail.com"})
    email_id = await builder.create_entity(email)

    phone = EntityNode(node_type="Device", properties={"type": "Phone", "number": "+1-555-019-8372"})
    phone_id = await builder.create_entity(phone)

    github = EntityNode(node_type="DigitalIdentity", properties={"type": "SocialProfile", "username": "ghost_99", "platform": "GitHub"})
    github_id = await builder.create_entity(github)

    ip = EntityNode(node_type="Device", properties={"type": "IPAddress", "ip": "192.168.1.105"})
    ip_id = await builder.create_entity(ip)

    btc = EntityNode(node_type="FinancialInstrument", properties={"type": "BitcoinWallet", "address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"})
    btc_id = await builder.create_entity(btc)

    print("Drawing Connections...")
    await builder.create_relationship(Relationship(source_id=john_id, target_id=email_id, rel_type="REGISTERED"))
    await builder.create_relationship(Relationship(source_id=john_id, target_id=phone_id, rel_type="OWNS"))
    await builder.create_relationship(Relationship(source_id=email_id, target_id=github_id, rel_type="LINKED_TO"))
    await builder.create_relationship(Relationship(source_id=github_id, target_id=ip_id, rel_type="LOGGED_IN_FROM"))
    await builder.create_relationship(Relationship(source_id=john_id, target_id=btc_id, rel_type="TRANSACTED_WITH"))

    print(f"Success! Dummy graph seeded.")
    print(f"Paste this ID into the Streamlit Network Graph tab to view it: {john_id}")
    
    await driver.close()

if __name__ == "__main__":
    asyncio.run(seed_dummy_graph())
