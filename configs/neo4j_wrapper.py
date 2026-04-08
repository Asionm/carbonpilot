# configs\neo4j_wrapper.py
from dotenv import load_dotenv
import os
from neo4j import GraphDatabase

# load .env file
load_dotenv(override=True)

class Neo4jWrapper:


    def __init__(self, uri=None, username=None, password=None):


        self.uri = uri or os.getenv("NEO4J_URI")
        self.username = username or os.getenv("NEO4J_USERNAME")
        self.password = password or os.getenv("NEO4J_PASSWORD")
        

        self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))

    def close(self):

        if self.driver:
            self.driver.close()

    def get_driver(self):

        return self.driver

    def execute_query(self, query, parameters=None):

        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def set_connection_info(self, uri=None, username=None, password=None):


        if self.driver:
            self.driver.close()
        

        self.uri = uri or self.uri
        self.username = username or self.username
        self.password = password or self.password
        

        self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
