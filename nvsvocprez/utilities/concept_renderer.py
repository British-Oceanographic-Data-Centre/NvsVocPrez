"""."""

from pyldapi.renderer import RDF_MEDIATYPES
from pyldapi import DisplayProperty, Renderer

from rdflib import Literal as RdfLiteral
from rdflib import Namespace
from rdflib.namespace import DC, DCTERMS, ORG, OWL, RDF, RDFS, SKOS, VOID
from starlette.responses import PlainTextResponse, Response

from utilities.system_configs import DATA_URI
from utilities.profiles import nvs, sdo, skos, vocpub, void
from utilities.utility_functions import (cache_return, exists_triple,
                   get_alt_profile_objects, get_alt_profiles,
                   get_ontologies, sparql_construct,
                   sparql_query)

from .templates import html_templates


class ConceptRenderer(Renderer):
    def __init__(self, request):
        self.request = request
        if "collection" in str(request.url):
            self.instance_uri = f"{DATA_URI}/collection/" + str(request.url).split("/collection/")[1].split("?")[0]
        elif "standard_name" in str(request.url):
            self.instance_uri = (
                f"{DATA_URI}/standard_name/" + str(request.url).split("/standard_name/")[1].split("?")[0]
            )

        concept_profiles = {
            "nvs": nvs,
            "skos": skos,
            "vocpub": vocpub,
            "sdo": sdo,
        }

        self.alt_profiles = get_alt_profiles()
        self.ontologies = get_ontologies()
        collection_uri = self.instance_uri.split("/current/")[0] + "/current/"
        for collection in cache_return(collections_or_conceptschemes="collections"):
            if collection["uri"]["value"] == collection_uri:
                concept_profiles.update(
                    get_alt_profile_objects(
                        collection,
                        self.alt_profiles,
                        ontologies=self.ontologies,
                        media_types=["text/html"] + RDF_MEDIATYPES,
                        default_mediatype="text/html",
                    )
                )

        super().__init__(request, self.instance_uri, concept_profiles, "nvs")

    def _render_sparql_response_rdf(self, sparql_response):
        if sparql_response[0]:
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?>\n'.encode() + sparql_response[1]
                if "xml" in self.mediatype
                else sparql_response[1],
                headers={"Content-Type": self.mediatype},
            )
        else:
            return PlainTextResponse(
                "There was an error obtaining the Concept RDF from the Triplestore",
                status_code=500,
            )

    def _render_nvs_or_profile_html(self):
        exclude_filters = ""
        prefixes = ""
        if self.profile != "nvs":
            exclude_filters += """
                FILTER ( ?p != skos:broader )
                FILTER ( ?p != skos:narrower )
                FILTER ( ?p != skos:related )
                FILTER ( ?p != owl:sameAs )
            """

        for ontology, data in self.ontologies.items():
            if ontology not in self.profiles[self.profile].ontologies:
                exclude_filters += f'FILTER (!STRSTARTS(STR(?p), "{data["url"]}"))\n'
            else:
                prefixes += f'PREFIX {data["prefix"]}: <{data["url"]}>\n'

        q = f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            {prefixes}
            SELECT DISTINCT ?p ?o ?o_label ?o_notation ?collection_uri ?collection_systemUri ?collection_label
            WHERE {{
              BIND (<{self.instance_uri}> AS ?concept)
              ?concept ?p ?o .
            
              FILTER ( ?p != skos:broaderTransitive )
              FILTER ( ?p != skos:narrowerTransitive )
              {exclude_filters}
              FILTER(!isLiteral(?o) || lang(?o) = "en" || lang(?o) = "")
            
              OPTIONAL {{
                ?o skos:prefLabel ?o_label ;
                   skos:notation ?o_notation .
                FILTER(!isLiteral(?o_label) || lang(?o_label) = "en" || lang(?o_label) = "")
              }}
            
              BIND(
                IF(
                  CONTAINS(STR(?concept), "standard_name"), 
                    <{DATA_URI}/standard_name/>,
                    IRI(CONCAT(STRBEFORE(STR(?concept), "/current/"), "/current/"))
                )
                AS ?collection_uri
              )
              BIND (REPLACE(STR(?collection_uri), "{DATA_URI}", "") AS ?collection_systemUri)
              OPTIONAL {{?collection_uri skos:prefLabel ?x }}
              BIND (COALESCE(?x, "Climate and Forecast Standard Names") AS ?collection_label)
            }}         
        """

        r = sparql_query(q)
        if not r[0]:
            return PlainTextResponse(
                "There was an error obtaining the Concept RDF from the Triplestore",
                status_code=500,
            )

        PAV = Namespace("http://purl.org/pav/")
        STATUS = Namespace("http://www.opengis.net/def/metamodel/ogc-na/")

        props = {
            str(DCTERMS.contributor): {"label": "Contributor", "group": "agent"},
            str(DCTERMS.creator): {"label": "Creator", "group": "agent"},
            str(DCTERMS.publisher): {"label": "Publisher", "group": "agent"},
            str(SKOS.notation): {"label": "Identifier", "group": "annotation"},
            # str(DCTERMS.identifier): {"label": "Identifier", "group": "annotation"},
            str(STATUS.status): {"label": "Status", "group": "annotation"},
            str(SKOS.altLabel): {"label": "Alternative Label", "group": "annotation"},
            str(SKOS.note): {"label": "Note", "group": "annotation"},
            str(SKOS.scopeNote): {"label": "Scope Note", "group": "annotation"},
            str(SKOS.historyNote): {"label": "History Note", "group": "annotation"},
            str(SKOS.notation): {"label": "Identifier", "group": "annotation"},
            str(OWL.sameAs): {"label": "Same As", "group": "related"},
            str(SKOS.broader): {"label": "Broader", "group": "related"},
            str(SKOS.related): {"label": "Related", "group": "related"},
            str(SKOS.narrower): {"label": "Narrower", "group": "related"},
            str(SKOS.exactMatch): {"label": "Exact Match", "group": "related"},
            str(SKOS.broadMatch): {"label": "Broad Match", "group": "related"},
            str(SKOS.closeMatch): {"label": "Close Match", "group": "related"},
            str(SKOS.narrowMatch): {"label": "Narrow Match", "group": "related"},
            str(PAV.hasCurrentVersion): {
                "label": "Has Current Version",
                "group": "provenance",
            },
            str(PAV.hasVersion): {"label": "Version", "group": "provenance"},
            str(OWL.deprecated): {"label": "Deprecated", "group": "provenance"},
            str(PAV.previousVersion): {
                "label": "Previous Version",
                "group": "provenance",
            },
            str(DCTERMS.isVersionOf): {"label": "Is Version Of", "group": "provenance"},
            str(PAV.authoredOn): {"label": "Authored On", "group": "provenance"},
            str(DC.identifier): {"group": "ignore"},
            str(DCTERMS.identifier): {"group": "ignore"},
            str(VOID.inDataset): {"group": "ignore"},
            str(RDF.type): {"group": "ignore"},
            str(OWL.versionInfo): {"group": "ignore"},
            str(PAV.authoredOn): {"group": "ignore"},
        }

        context = {
            "request": self.request,
            "deprecated": False,
            "prefLabel": None,
            "uri": self.instance_uri,
            "collection_systemUri": None,
            "collection_label": None,
            "definition": None,
            "date": None,
            "altLabels": [],
            "profile_properties": [],
            "annotation": [],
            "agent": [],
            "related": [],
            "provenance": [],
            "other": [],
            "profile_token": self.profile,
            "alt_profiles": self.alt_profiles,
            "profile_properties_for_button": [],
        }

        def make_predicate_label_from_uri(uri):
            return uri.split("#")[-1].split("/")[-1]

        alt_profiles = get_alt_profiles()
        profile_url = None

        for ap in alt_profiles.values():
            if ap["token"] == self.profile:
                profile_url = ap["url"]
                context["profile"] = ap

        for x in r[1]:
            p = x["p"]["value"]
            o = x["o"]["value"]
            o_label = x["o_label"]["value"] if x.get("o_label") is not None else None
            o_notation = x["o_notation"]["value"] if x.get("o_notation") is not None else None

            context["collection_systemUri"] = x["collection_systemUri"]["value"]
            context["collection_label"] = x["collection_label"]["value"]
            if p == str(OWL.deprecated):
                if o == "true":
                    context["deprecated"] = True
            elif p == str(SKOS.prefLabel):
                context["prefLabel"] = o
            elif p == str(SKOS.altLabel):
                if o not in context["altLabels"]:
                    context["altLabels"].append(o)

            elif p == str(SKOS.definition):
                context["definition"] = o
            elif p == str(DCTERMS.date):
                context["date"] = o.replace(" ", "T").rstrip(".0")
            elif p in props.keys():
                if props[p]["group"] != "ignore":
                    context[props[p]["group"]].append(DisplayProperty(p, props[p]["label"], o, o_label, o_notation))
            elif profile_url and p.startswith(profile_url):
                p_label = p[len(profile_url) :]
                if p_label[0] == "#":
                    p_label = p_label[1:]

                context["profile_properties"].append(DisplayProperty(p, p_label, o, o_label, o_notation))
            else:
                context["other"].append(DisplayProperty(p, make_predicate_label_from_uri(p), o, o_label))

        def clean_prop_list_labels(prop_list):
            last_pred_html = None
            for x in prop_list:
                this_predicate_html = x.predicate_html
                if this_predicate_html == last_pred_html:
                    x.predicate_html = ""
                last_pred_html = this_predicate_html

        context["altLabels"].sort()
        context["profile_properties"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["profile_properties"])
        context["agent"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["agent"])
        context["annotation"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["annotation"])
        context["related"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["related"])
        context["provenance"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["provenance"])
        context["other"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["other"])

        q1 = f"""
             PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
             PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
             PREFIX dcterms: <http://purl.org/dc/terms/>
             PREFIX owl: <http://www.w3.org/2002/07/owl#>
        
             SELECT ?id ?systemUri
             (GROUP_CONCAT(?conformsto;SEPARATOR=",") AS ?conforms_to)
             WHERE {{
                ?uri a skos:Collection .             
                BIND (STRAFTER(STRBEFORE(STR(?uri), "/current/"), "/collection/") AS ?id)
                BIND (STRAFTER(STR(?uri), ".uk") AS ?systemUri)
                OPTIONAL {{ ?uri dcterms:conformsTo ?conformsto }}
            }}
            group by ?uri ?id ?systemUri
         """
        r1 = sparql_query(q1)

        q2 = f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT DISTINCT ?p ?o ?o_label ?o_notation ?collection_uri ?collection_systemUri ?collection_label
            WHERE {{
              BIND (<{self.instance_uri}> AS ?concept)
              ?concept ?p ?o .

              FILTER ( ?p != skos:broaderTransitive )
              FILTER ( ?p != skos:narrowerTransitive )
              FILTER ( ?p != skos:broader )
              FILTER ( ?p != skos:narrower )
              FILTER ( ?p != skos:related )
              FILTER ( ?p != owl:sameAs )
              FILTER(!isLiteral(?o) || lang(?o) = "en" || lang(?o) = "")

              OPTIONAL {{
                ?o skos:prefLabel ?o_label ;
                   skos:notation ?o_notation .
                FILTER(!isLiteral(?o_label) || lang(?o_label) = "en" || lang(?o_label) = "")
              }}

              BIND(
                IF(
                  CONTAINS(STR(?concept), "standard_name"),
                    <{DATA_URI}/standard_name/>,
                    IRI(CONCAT(STRBEFORE(STR(?concept), "/current/"), "/current/"))
                )
                AS ?collection_uri
              )
              BIND (REPLACE(STR(?collection_uri), "{DATA_URI}", "") AS ?collection_systemUri)
              OPTIONAL {{?collection_uri skos:prefLabel ?x }}
              BIND (COALESCE(?x, "Climate and Forecast Standard Names") AS ?collection_label)
            }}
        """

        r2 = sparql_query(q2)

        p_keys = [x["p"]["value"] for x in r2[1]]

        context["conforms_to"] = []

        for item in r1[1]:
            if "conforms_to" in item and item["systemUri"]["value"] in context["uri"]:
                c = item["conforms_to"]["value"].split(",")
                for c_item in c:
                    match = any(c_item in s for s in p_keys)
                    if match:
                        context["conforms_to"].append(c_item)

        return html_templates.TemplateResponse("concept.html", context=context)

    def _render_nvs_rdf(self):
        exclude_filters = ""
        for ontology in self.ontologies.values():
            exclude_filters += f'FILTER (!STRSTARTS(STR(?p), "{ontology["url"]}"))\n'

        q = f"""
            PREFIX dc: <http://purl.org/dc/terms/>
            PREFIX dce: <http://purl.org/dc/elements/1.1/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX pav: <http://purl.org/pav/>
            PREFIX prov: <https://www.w3.org/ns/prov#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX void: <http://rdfs.org/ns/void#>

            CONSTRUCT {{
              <{self.instance_uri}> ?p ?o .

              # remove provenance, for now
              # ?s ?p2 ?o2 .              
              # ?s rdf:subject <{self.instance_uri}> ;
              #   prov:has_provenance ?m .              
            }}
            WHERE {{
                <{self.instance_uri}> ?p ?o .

                # remove provenance, for now
                # OPTIONAL {{
                #     ?s rdf:subject <{self.instance_uri}> ;
                #        prov:has_provenance ?m .
                #         
                #     # {{ ?s ?p2 ?o2 }}
                # }}

                # exclude altprof properties from NVS view
                {exclude_filters}
            }}
        """
        return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

    def _render_skos_rdf(self):
        q = """
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            CONSTRUCT {
              <xxx> ?p ?o .   
              ?s ?p2 <xxx> .  
            }
            WHERE {
              <xxx> ?p ?o .
              ?s ?p2 <xxx> .

              # include only SKOS properties
              FILTER (STRSTARTS(STR(?p), "http://www.w3.org/2004/02/skos/core#"))
              FILTER (STRSTARTS(STR(?p2), "http://www.w3.org/2004/02/skos/core#"))
            }
            """.replace(
            "xxx", self.instance_uri
        )
        return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

    def _render_vocpub_rdf(self):
        q = """
            PREFIX dce: <http://purl.org/dc/elements/1.1/>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX pav: <http://purl.org/pav/>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX void: <http://rdfs.org/ns/void#>
            CONSTRUCT {
              <xxx> ?p ?o .   
              ?s ?p2 <xxx> .  
            }
            WHERE {
              <xxx> ?p ?o .
              ?s ?p2 <xxx> .

              FILTER (!STRSTARTS(STR(?p2), "http://www.w3.org/1999/02/22-rdf-syntax-ns#"))
            }
            """.replace(
            "xxx", self.instance_uri
        )
        return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

    def _render_sdo_rdf(self):
        q = """
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX sdo: <https://schema.org/>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            CONSTRUCT {
              <DATA_URI/collection/P01/current/SAGEMSFM/>
                a sdo:DefinedTerm ;
                sdo:name ?pl ;
                sdo:alternateName ?al ;
                sdo:description ?def ;
                sdo:identifier ?id ;
                sdo:dateModified ?modified ;
                sdo:version ?versionInfo ;
                sdo:inDefinedTermSet ?collection ;
                sdo:isPartOf ?scheme ;
                sdo:sameAs ?sameAs ;
              .
            }
            WHERE {
              <DATA_URI/collection/P01/current/SAGEMSFM/> 
                skos:prefLabel ?pl ;
                skos:definition ?def ;
                dcterms:identifier ?id ;
                dcterms:date ?date ;
                owl:versionInfo ?versionInfo ;
              .

              BIND (STRDT(REPLACE(STRBEFORE(?date, "."), " ", "T"), xsd:dateTime) AS ?modified)

              ?collection skos:member <DATA_URI/collection/P01/current/SAGEMSFM/>  .

              OPTIONAL {
                <DATA_URI/collection/P01/current/SAGEMSFM/>
                  skos:altLabel ?al ;
                  skos:inScheme ?scheme ;
                  owl:sameAs ?sameAs ;
                .
              }
            }            
            """.replace(
            "DATA_URI", DATA_URI
        )
        return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

    def _render_profile_rdf(self):
        exclude_filters = ""
        prefixes = ""

        for ontology, data in self.ontologies.items():
            if ontology not in self.profiles[self.profile].ontologies:
                exclude_filters += f'FILTER (!STRSTARTS(STR(?p), "{data["url"]}"))\n'
            else:
                prefixes += f'PREFIX {data["prefix"]}: <{data["url"]}>\n'

        q = f"""
            PREFIX dc: <http://purl.org/dc/terms/>
            PREFIX dce: <http://purl.org/dc/elements/1.1/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX pav: <http://purl.org/pav/>
            PREFIX prov: <https://www.w3.org/ns/prov#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX void: <http://rdfs.org/ns/void#>
            {prefixes}

            CONSTRUCT {{
              <{self.instance_uri}> ?p ?o .
            }}
            WHERE {{
              <{self.instance_uri}> ?p ?o .
              FILTER ( ?p != skos:broaderTransitive )
              FILTER ( ?p != skos:narrowerTransitive )
              FILTER ( ?p != skos:broader )
              FILTER ( ?p != skos:narrower )
              FILTER ( ?p != skos:related )
              FILTER ( ?p != owl:sameAs )
              # exclude other properties from altprof
              {exclude_filters}
            }}
        """
        return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

    def render(self):
        alt_profile_tokens = [alt["token"] for alt in self.alt_profiles.values()]
        if self.profile == "nvs":
            if self.mediatype in RDF_MEDIATYPES or self.mediatype in Renderer.RDF_SERIALIZER_TYPES_MAP:
                return self._render_nvs_rdf()
            else:
                return self._render_nvs_or_profile_html()
        elif self.profile == "skos":
            return self._render_skos_rdf()
        elif self.profile == "vocpub":
            return self._render_vocpub_rdf()
        elif self.profile == "sdo":
            return self._render_sdo_rdf()
        elif self.profile in alt_profile_tokens:
            if self.mediatype in RDF_MEDIATYPES or self.mediatype in Renderer.RDF_SERIALIZER_TYPES_MAP:
                return self._render_profile_rdf()
            else:
                return self._render_nvs_or_profile_html()

        alt = super().render()
        if alt is not None:
            return alt
