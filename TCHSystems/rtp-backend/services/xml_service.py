from lxml import etree as lxml_etree
import xml.etree.ElementTree as ET
import uuid
from datetime import datetime, timezone

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
                <xs:complexType><xs:sequence><xs:element name="MsgId" type="xs:string"/><xs:element name="CreDtTm" type="xs:string"/></xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="CdtTrfTxInf">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="PmtId">
                      <xs:complexType><xs:sequence><xs:element name="EndToEndId" type="xs:string"/></xs:sequence></xs:complexType>
                    </xs:element>
                    <xs:element name="IntrBkSttlmAmt">
                      <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal"><xs:attribute name="Ccy" type="xs:string"/></xs:extension></xs:simpleContent></xs:complexType>
                    </xs:element>
                    <xs:element name="DbtrAgt" type="AgentType"/>
                    <xs:element name="Dbtr" type="PartyType"/>
                    <xs:element name="DbtrAcct" type="AccountType"/>
                    <xs:element name="CdtrAgt" type="AgentType"/>
                    <xs:element name="Cdtr" type="PartyType"/>
                    <xs:element name="CdtrAcct" type="AccountType"/>
                    <xs:element name="RmtInf" minOccurs="0">
                        <xs:complexType><xs:sequence><xs:element name="Ustrd" type="xs:string"/></xs:sequence></xs:complexType>
                    </xs:element>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:complexType name="AgentType"><xs:sequence><xs:element name="FinInstnId"><xs:complexType><xs:sequence><xs:element name="ClrSysMmbId"><xs:complexType><xs:sequence><xs:element name="nm" type="xs:string"/><xs:element name="MmbId" type="xs:string"/></xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType>
  <xs:complexType name="PartyType"><xs:sequence><xs:element name="Nm" type="xs:string"/></xs:sequence></xs:complexType>
  <xs:complexType name="AccountType"><xs:sequence><xs:element name="Id"><xs:complexType><xs:sequence><xs:element name="Othr"><xs:complexType><xs:sequence><xs:element name="Id" type="xs:string"/><xs:element name="SchmeNm"><xs:complexType><xs:sequence><xs:element name="Prtry" type="xs:string"/></xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType>
</xs:schema>
"""

PACS002_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" 
           targetNamespace="urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10" 
           xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10" 
           elementFormDefault="qualified">
  <xs:element name="Document">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="FIToFIPmtStsRpt">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="GrpHdr" type="xs:anyType"/>
              <xs:element name="OrgnlGrpInfAndSts" type="xs:anyType"/>
              <xs:element name="TxInfAndSts">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="OrgnlEndToEndId" type="xs:string"/>
                    <xs:element name="TxSts" type="xs:string"/>
                    <xs:any processContents="skip" minOccurs="0" maxOccurs="unbounded"/>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""

# pacs.008
schema_root = lxml_etree.XML(ISO_20022_XSD.encode('utf-8'))
iso_schema = lxml_etree.XMLSchema(schema_root)

def validate_xml_schema(xml_string: str):
    xml_doc = lxml_etree.fromstring(xml_string.encode('utf-8'))
    iso_schema.assertValid(xml_doc)

# pacs.002
pacs002_schema_root = lxml_etree.XML(PACS002_XSD.encode('utf-8'))
pacs002_iso_schema = lxml_etree.XMLSchema(pacs002_schema_root)

def validate_pacs002_schema(xml_string: str):
    xml_doc = lxml_etree.fromstring(xml_string.encode('utf-8'))
    pacs002_iso_schema.assertValid(xml_doc)

def extract_rtp_data(xml_string: str):
    root = ET.fromstring(xml_string)
    msg_id_node = root.find('.//{*}GrpHdr//{*}MsgId')
    end_to_end_node = root.find('.//{*}PmtId//{*}EndToEndId')
    amount_node = root.find('.//{*}IntrBkSttlmAmt')
    sender_node = root.find('.//{*}DbtrAgt//{*}FinInstnId//{*}ClrSysMmbId//{*}nm')
    receiver_node = root.find('.//{*}CdtrAgt//{*}FinInstnId//{*}ClrSysMmbId//{*}nm')
    debtor_name_node = root.find('.//{*}Dbtr//{*}Nm')
    debtor_account_node = root.find('.//{*}DbtrAcct//{*}Id//{*}Othr//{*}Id')
    if debtor_account_node is None: debtor_account_node = root.find('.//{*}DbtrAcct//{*}Id')
    creditor_name_node = root.find('.//{*}Cdtr//{*}Nm')
    creditor_account_node = root.find('.//{*}CdtrAcct//{*}Id//{*}Othr//{*}Id')
    if creditor_account_node is None: creditor_account_node = root.find('.//{*}CdtrAcct//{*}Id')
    sender_rtn_node = root.find('.//{*}DbtrAgt//{*}MmbId')
    receiver_rtn_node = root.find('.//{*}CdtrAgt//{*}MmbId')
    ustrd_node = root.find('.//{*}RmtInf//{*}Ustrd')
    
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
        "creditor_account": creditor_account_node.text if creditor_account_node is not None else None,
        "sender_rtn": sender_rtn_node.text if sender_rtn_node is not None else None,
        "receiver_rtn": receiver_rtn_node.text if receiver_rtn_node is not None else None,
        "description": ustrd_node.text if ustrd_node is not None else "No description",
    }

def extract_pacs002_data(xml_string: str):
    """Odczytuje status i ID transakcji z odpowiedzi pacs.002 od banku docelowego"""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_string.encode('utf-8'))
    
    e2e_node = root.find('.//{*}OrgnlEndToEndId')
    status_node = root.find('.//{*}TxSts')
    
    if status_node is None:
        status_node = root.find('.//{*}GrpSts')
        
    if e2e_node is None or status_node is None:
        raise ValueError("Missing OrgnlEndToEndId or TxSts in pacs.002 message.")
        
    return {
        "end_to_end_id": e2e_node.text,
        "status": status_node.text  # 'ACCP' lub 'RJCT'
    }

def generate_pacs002(data: dict, status: str) -> str:
    msg_id = f"MSG-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    cre_dt_tm = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    acct_svcr_ref = f"REF-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    
    e2e_id = data.get("end_to_end_id", "E2E-UNKNOWN")
    org_msg_id = data.get("msg_id", e2e_id)
    sender_nm = data.get("sender_name", "UNKNOWN_SENDER")
    receiver_nm = data.get("receiver_name", "UNKNOWN_RECEIVER")
    amount = str(data.get("amount", "0.00"))
    currency = data.get("currency", "USD")
    dbtr_nm = data.get("debtor_name", "UNKNOWN")
    dbtr_acct = data.get("debtor_account", "UNKNOWN")
    cdtr_nm = data.get("creditor_name", "UNKNOWN")
    cdtr_acct = data.get("creditor_account", "UNKNOWN")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10">
    <FIToFIPmtStsRpt>
        <GrpHdr>
            <MsgId>{msg_id}</MsgId>
            <CreDtTm>{cre_dt_tm}</CreDtTm>
            <InstgAgt>
                <FinInstnId>
                    <Nm>{sender_nm}</Nm>
                </FinInstnId>
            </InstgAgt>
            <InstdAgt>
                <FinInstnId>
                    <Nm>{receiver_nm}</Nm>
                </FinInstnId>
            </InstdAgt>
        </GrpHdr>
        <OrgnlGrpInfAndSts>
            <OrgnlMsgId>{org_msg_id}</OrgnlMsgId>
            <GrpSts>{status}</GrpSts>
        </OrgnlGrpInfAndSts>
        <TxInfAndSts>
            <OrgnlEndToEndId>{e2e_id}</OrgnlEndToEndId>
            <TxSts>{status}</TxSts>
            <AcctSvcrRef>{acct_svcr_ref}</AcctSvcrRef>
            <OrgnlTxRef>
                <IntrBkSttlmAmt Ccy="{currency}">{amount}</IntrBkSttlmAmt>
                <Dbtr>
                    <Nm>{dbtr_nm}</Nm>
                </Dbtr>
                <DbtrAcct>
                    <Id>
                        <Othr>
                            <Id>{dbtr_acct}</Id>
                            <SchmeNm><Prtry>US_ACCT</Prtry></SchmeNm>
                        </Othr>
                    </Id>
                </DbtrAcct>
                <Cdtr>
                    <Nm>{cdtr_nm}</Nm>
                </Cdtr>
                <CdtrAcct>
                    <Id>
                        <Othr>
                            <Id>{cdtr_acct}</Id>
                            <SchmeNm><Prtry>US_ACCT</Prtry></SchmeNm>
                        </Othr>
                    </Id>
                </CdtrAcct>
            </OrgnlTxRef>
        </TxInfAndSts>
    </FIToFIPmtStsRpt>
</Document>"""

def is_valid_rtn(rtn: str) -> bool:
    # sprawdź czy to 9 cyfr
    if not (len(rtn) == 9 and rtn.isdigit()):
        return False
    
    # przekształć na listę liczb
    d = [int(digit) for digit in rtn]
    
    # wzór (3(d1+d4+d7) + 7(d2+d5+d8) + 1(d3+d6+d9)) mod 10 = 0
    # Indeksy d1=0, d2=1, d3=2, d4=3, d5=4, d6=5, d7=6, d8=7, d9=8
    checksum = (
        3 * (d[0] + d[3] + d[6]) + 
        7 * (d[1] + d[4] + d[7]) + 
        1 * (d[2] + d[5] + d[8])
    )
    
    return checksum % 10 == 0