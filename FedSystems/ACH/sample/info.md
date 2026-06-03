# Bagguette bank (2 batches):

## Bank client

* $100 -> LeekBank client (code 22 credits to other account) (Baguette bank client sends money)
* $31 <- CroissantBank (code 27 pull request from CroissantBank) (Baguette bank client wants to recive money)

## Baguette Store

* $310 -> LeekBank (code 22)

# LeekBank (1 batch)

## Leek Store

* $39 -> CroissantBank (code 22)
* $39 -> BaguetteBank (code 22)

## CroissantBank

* $500 <- LeekBank (code 27)
* $500 <- BaguetteBank (code 27)
* $500 <- BankOfTheOnion (code 27)

# Bank of the Onion

Their .ach file is broken on purpose and should not pass the collection.


# Summary

* Bagguete bank sends $410 to LeekBank, but recives $39 back from them, so they should only send them $371
* Leek Bank sends $39 to BaguetteBank, but recives $410 from them, so they should not send them any money.

* Bagguete bank wants to recive $31 from Croissant Bank but Croissant Bank wants to recive $500 from them. So Bagguete bank needs to send $469 to Croissant Bank.
* Croissant Bank wants to recive $500 from Baguette Bank, but Baguette Bank also wants to recive $39 from them. So Croissant Bank doesn't need to send them any money.

---

* Leek bank is sending $39 to Croissant Bank, but Croissant Bank wants to recive additional $500 from them. So Leek bank will need to send them $539.

---

* Croissant Bank wants to recive $500 from onion bank, Onion bank didn't send .ach file (it failed collection) so they have to send Croissant Bank $500
