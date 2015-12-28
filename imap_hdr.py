import imaplib
import pytz
import datetime
import pprint
import email
import json
import traceback

from encoder import NoIndent, MyEncoder
from imap_conn import open_connection


def date_to_UTC(orig_date):
    """
    A function to convert a formatted string containing date and time from a local timezone to UTC, by taking into
    consideration multiple formats of the input parameter
    :param orig_date: Formatted string containing a date and time from a local timezone
    :return: Formatted string containing the date and time in UTC
    """

    try:
        # Truncating the string to contain only required values and removing unwanted whitespace
        trunc_date = orig_date[:31] if len(orig_date) > 31 else orig_date
        trunc_date = trunc_date.strip()

        # Generating a datetime object considering multiple formats of the input parameter - with and without weekday
        if len(trunc_date) < 27:
            datetime_obj = datetime.datetime.strptime(trunc_date, "%d %b %Y %H:%M:%S %z")
        else:
            datetime_obj = datetime.datetime.strptime(trunc_date, "%a, %d %b %Y %H:%M:%S %z")

        # Converting the datetime object into a formatted string
        utc_dt = datetime_obj.astimezone(pytz.utc)
        return utc_dt.strftime("%a, %d %b %Y %H:%M:%S %z")

    except:
        print("Unable to process date:", orig_date, trunc_date)
        traceback.print_exc()


def get_mail_header(to_get=2000, range_=True):
    """
    This function fetches the emails from the IMAP server as per the parameters passed.
    :param to_get: List of UIDs of the mails to get. Default value is 2000.
    :param range_: If true, fetches all emails from the first element in to_get, till the newest mail.
    If false, fetches only the emails with the UIDs present in to_get. Default value is true.
    """
    # This is used to map the string in the Message-Id field of the header to the UID of the mail.
    # By doing so we ease the further processing of information.
    uid_msg_id_map = {}

    """
    The issue lies in with the fact that we are trying to download a whole list of messages in the inbox at once.
    This causes a buffer overflow and hence imaplib raises an error(the max it allows, by default, is 10000 bytes).
    So, one possible solution is to change the _MAXLINE value to a bigger number.
    Also gmail has no problem with a search this big.
    """
    imaplib._MAXLINE = 800000

    # Connection object for gmail inbox
    conn = open_connection()


    try:
        # Selecting the inbox from which mails will be fetched
        conn.select('INBOX')

        # Variable to keep track of the number of unseen messages in the chosen mailbox
        processed_msgs = 0

        # Searching mailbox for messages with UID from 2000 till the newest mail in inbox
        if range_:
            search_str = 'UID ' + str(to_get[0]) + ':*'
            retcode, uids = conn.uid('SEARCH', None, search_str)
            to_get.clear()
            for uid in uids[0].split():
                to_get.append(int(uid))
        else:
            retcode = "OK"

        num_of_messages = len(to_get)

        #print(uids)
        print("Number of messages to fetch:", num_of_messages)

        # retcode indicates the success or failure of the imap request
        if retcode == "OK":
            # header.json file will store all the required data
            with open("headers.json", mode='a', encoding='utf-8') as f:

                for num in to_get:

                    print('Processing mail #', num)
                    processed_msgs += 1

                    # conn.uid() converts the arguments provided to an IMAP command to fetch the mail using the UID sepcified by num
                    # Uncomment the line below to fetch the entire message rather than just the mail headers.
                    # typ, msg_header = conn.uid('FETCH', num, '(RFC822)')

                    typ, msg_header = conn.uid('FETCH', str(num), '(RFC822.HEADER)')

                    # print(msg_header)

                    for response_part in msg_header:
                        if isinstance(response_part, tuple):

                            # response_part contains the required info as a byte stream. This has to be converted to a message stream.
                            # This is done using the email module
                            original = email.message_from_bytes(response_part[1])

                            # The splicing is done as to remove the '<' and '>' from the message-id string
                            uid_msg_id_map[original['Message-ID'][1:-1]] = num

                            data = {}
                            data['Message-ID'] = num
                            data['From'] = original['From']
                            data['To'] = original['To']
                            data['Cc'] = original['Cc']
                            data['In-Reply-To'] = original['In-Reply-To']
                            data['Time'] = date_to_UTC(original['Date'])

                            if original['References'] is None:
                                data['References'] = None
                            else:
                                uid_list = []
                                """
                                Since all the references are also in string, we have to go through each string in the list of references.
                                For each references string in the list, we check if we have already encountered it. In such a case, we
                                associate the the UID of the mail that had the first occurence of this string.
                                If not, we just append the value 0.
                                Also splicing is done for references to remove '<' and '>'
                                """

                                for references in original['References'].split():
                                    if not (references[1:-1] in list(uid_msg_id_map.keys())):
                                        uid_msg_id_map[references[1:-1]] = 0
                                    uid_list.append(uid_msg_id_map[references[1:-1]])

                                """
                                Each element of a list, when written into a .json file take a line each. To pretty print it we make
                                it an object of NoIndent class and use a custom encoder class called MyEncoder
                                """
                                data['References'] = NoIndent(uid_list)

                            json.dump(data, f, cls=MyEncoder, indent=1)
                            f.write("\n")

                # Marking all message as seen
                typ, msg_header = conn.uid('STORE', str(num), '+FLAGS', '\\Seen')

                f.close()
        print("Number of messages processed:", processed_msgs)
    finally:
        try:
            conn.close()
        except:
            pass
        conn.logout()
