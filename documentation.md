# Disclaimer & Reference Scope
This documentation is intended as a high-level reference for the operational logic of real-world payment systems. The information provided has been synthesized from public records and third-party research to the best of our current ability.

**Please note**: This project is a functional representation rather than a 100% authoritative specification. It includes necessary design assumptions where official documentation was either unavailable or where we may have been unaware of its existence. We recognize that certain proprietary details or obscure technical standards may not be fully reflected in this model.

For the specific implementation details of this project, see:
* Federal Reserve Systems: `FedSystems/documentation.md`
* The Clearing House Systems: `TCH/documentation.md`

# Fed systems
The ACH and FedNow rails are both operated by the Federal Reserve. While ACH and FedNow serve different purposes regarding settlement speed, they share certain infrastructural components and regulatory oversight.
## ACH


## FedNow


# TCH systems
Real-Time Payments (RTP) is the private-sector counterpart to FedNow. It is decoupled from the Fed Systems in this project because it operates on a separate private rail and requires independent API handling and settlement logic.

## RTP