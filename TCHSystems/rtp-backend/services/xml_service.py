from lxml import etree as lxml_etree
import xml.etree.ElementTree as ET

ISO_20022_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" 
           targetNamespace="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08" 
           xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08" 
           elementFormDefault="qualified">
  <xs:element name="Document">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="FIToFICstmrCdtTrf">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="GrpHdr">
                <xs:complexType><xs:sequence><xs:element name="MsgId" type="xs:string"/></xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="CdtTrfTxInf">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="PmtId">
                      <xs:complexType><xs:sequence><xs:element name="EndToEndId" type="xs:string"/></xs:sequence></xs:complexType>
                    </xs:element>
                    <xs:element name="IntrBkSttlmAmt">
                      <xs:complexType>
                        <xs:simpleContent>
                          <xs:extension base="xs:decimal"><xs:attribute name="Ccy" type="xs:string" use="required"/></xs:extension>
                        </xs:simpleContent>
                      </xs:complexType>
                    </xs:element>
                    <xs:element name="DbtrAgt" type="AgentType"/>
                    <xs:element name="Dbtr" type="PartyType"/>
                    <xs:element name="DbtrAcct" type="AccountType"/>
                    <xs:element name="CdtrAgt" type="AgentType"/>
                    <xs:element name="Cdtr" type="PartyType"/>
                    <xs:element name="CdtrAcct" type="AccountType"/>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:complexType name="AgentType"><xs:sequence><xs:element name="FinInstnId"><xs:complexType><xs:sequence><xs:element name="ClrSysMmbId"><xs:complexType><xs:sequence><xs:element name="MmbId" type="xs:string"/></xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType>
  <xs:complexType name="PartyType"><xs:sequence><xs:element name="Nm" type="xs:string"/></xs:sequence></xs:complexType>
  <xs:complexType name="AccountType"><xs:sequence><xs:element name="Id"><xs:complexType><xs:sequence><xs:element name="Othr"><xs:complexType><xs:sequence><xs:element name="Id" type="xs:string"/></xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType>
</xs:schema>
"""

schema_root = lxml_etree.XML(ISO_20022_XSD.encode('utf-8'))
iso_schema = lxml_etree.XMLSchema(schema_root)

def validate_xml_schema(xml_string: str):
    xml_doc = lxml_etree.fromstring(xml_string.encode('utf-8'))
    iso_schema.assertValid(xml_doc)

def extract_rtp_data(xml_string: str):
    root = ET.fromstring(xml_string)
    msg_id_node = root.find('.//{*}GrpHdr//{*}MsgId')
    end_to_end_node = root.find('.//{*}PmtId//{*}EndToEndId')
    amount_node = root.find('.//{*}IntrBkSttlmAmt')
    sender_node = root.find('.//{*}DbtrAgt//{*}FinInstnId//{*}ClrSysMmbId//{*}MmbId')
    receiver_node = root.find('.//{*}CdtrAgt//{*}FinInstnId//{*}ClrSysMmbId//{*}MmbId')
    debtor_name_node = root.find('.//{*}Dbtr//{*}Nm')
    debtor_account_node = root.find('.//{*}DbtrAcct//{*}Id//{*}Othr//{*}Id')
    if debtor_account_node is None: debtor_account_node = root.find('.//{*}DbtrAcct//{*}Id')
    creditor_name_node = root.find('.//{*}Cdtr//{*}Nm')
    creditor_account_node = root.find('.//{*}CdtrAcct//{*}Id//{*}Othr//{*}Id')
    if creditor_account_node is None: creditor_account_node = root.find('.//{*}CdtrAcct//{*}Id')
    
    if None in (amount_node, sender_node, receiver_node, msg_id_node, end_to_end_node):
        raise ValueError("Missing required ISO 20022 tags.")
        
    return {
        "msg_id": msg_id_node.text,
        "end_to_end_id": end_to_end_node.text,
        "amount": float(amount_node.text),
        "currency": amount_node.attrib.get('Ccy'),
        "sender_code": sender_node.text,
        "receiver_code": receiver_node.text,
        "debtor_name": debtor_name_node.text if debtor_name_node is not None else None,
        "debtor_account": debtor_account_node.text if debtor_account_node is not None else None,
        "creditor_name": creditor_name_node.text if creditor_name_node is not None else None,
        "creditor_account": creditor_account_node.text if creditor_account_node is not None else None
    }