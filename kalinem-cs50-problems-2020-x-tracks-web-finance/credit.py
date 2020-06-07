import re

# Checks if the given credit card number is valid
def checksum(number):

    # Variables to be used later
    amex = False
    visa = False
    mc = False
    valid = False
    if number is str:
        length = len(number)
    else:
        number = str(number)
        length = len(str(number))

    # If it's not a number:
    if not number.isnumeric():
        return (1, "not a number")

    # Check if starting numbers are valid
    if re.search("^4", number) and length in {13, 16}:
        visa = True
    elif re.search("^3[47]", number) and length == 15:
        amex = True
    elif re.search("^5[1-5]", number) and length == 16:
        mc = True
    else:
        return (2, "invalid")

    # Checks if it satisfies math constraint
    checksum = 0
    number = int(number)
    copy = int(number / 10)

    # Add 2 * every other digit starting with the 2nd to last number
    while copy > 0:
        # Adds each digit depending on length of number
        digit = 2 * (copy % 10)
        for i in range(len(str(digit))):
            checksum += digit % 10
            digit = int(digit/10)

        # Go to the next digit
        copy = int(copy / 100)

    # Add the remaining digits
    while number > 0:
        checksum += number % 10

        # Go to next digit
        number = int(number / 100)

    # Check whether checksum = 0 mod 10
    if checksum % 10 == 0:
        valid = True

    # Return invalid if invalid
    if not valid:
        return (2, "invalid")

    # Else it's valid and we return which type
    if amex:
        result = (0, "AMEX")
    elif visa:
        result = (0, "VISA")
    elif mc:
        result = (0, "MASTERCARD")

    return result
