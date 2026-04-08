import os
import subprocess
from dotenv import load_dotenv

def create_neo4j_container(container_name="neo4j-carbon"):
    """
    Create a Neo4j Docker container using username/password from .env
    No port check, no container check, no volume mapping.
    """
    load_dotenv(".env")

    neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "neo4j")

    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", "7474:7474",
        "-p", "7687:7687",
        "-e", f"NEO4J_AUTH={neo4j_username}/{neo4j_password}",
        "neo4j:latest"
    ]

    print(f"▶ Creating Neo4j container: {container_name} ...")
    subprocess.run(cmd, check=True)
    print("✔ Neo4j container created successfully!")
