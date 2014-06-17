# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2010-2014 Elico Corp. All Rights Reserved.
#    Alex Duan <alex.duan@elico-corp.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp.addons.account_statement_base_import.parser\
    import generic_file_parser
from openerp.addons.account_statement_base_import.parser.parser\
    import UnicodeDictReader
from openerp.osv.osv import except_osv
from openerp.tools.translate import _
import datetime
import tempfile
import fileinput


class FCTFileParser(generic_file_parser.FileParser):
    '''This is a class that parser the following format csv:
    Col1 Col2    Col3    Col4    Col5    Col6    Col7    Col8    Col9
        Col10   Col11   Col12
    "Record Type","Account Number","Transaction Code","Reference",
        "Narrative","Amount","Transaction Amount Type","Post Date","Value Date"
        *****
        parse process:
            self._format(*args, **kwargs)
            self._pre(*args, **kwargs)   ----   "pre-treatment"
            self._parse(*args, **kwargs)
            self._validate(*args, **kwargs)
            self._post(*args, **kwargs)
    '''
    def __init__(self, parse_name, ftype='csv', **kwags):
        super(self.__class__, self).__init__(parse_name, ftype=ftype, **kwags)
        self.conversion_dict = {
            'Post Date': datetime.datetime,
            'Value Date': datetime.datetime,
            'Transaction Amount Type': unicode,
            'Amount': unicode,
            'Reference': unicode,
            'Narrative': unicode,
        }
        self.keys_to_validate = self.conversion_dict.keys()

    @classmethod
    def parser_for(cls, parser_name):
        """
        Used by the new_bank_statement_parser class factory. Return true if
        the providen name is FCT_bank_statement_csv
        """
        return parser_name == ('FCT_bank_statement_csv')

    def _validate(self, *args, **kwargs):
        return super(self.__class__, self)._validate(*args, **kwargs)

    def _from_csv(self, result_set, conversion_rules):
        """
        Handle the converstion from the dict and handle date format from
        an .csv file.
        rewrite this method and do the date converstion.
        """
        date_format = '%M/%d/%Y'
        for line in result_set:
            for rule in conversion_rules:
                if conversion_rules[rule] == datetime.datetime:
                    try:
                        date_string = line[rule].split(' ')[0]
                        date_string = datetime.datetime.strptime(
                            date_string,
                            date_format)
                        line[rule] = date_string.strftime('%Y-%m-%d')
                    except ValueError as err:
                        raise except_osv(_("Date format is not valid."),
                                         _(" It should be YYYY-MM-DD for column: %s"
                                           " value: %s \n \n"
                                           " \n Please check the line with ref: %s"
                                           " \n \n Detail: %s") % (rule,
                                                                   line.get(rule, _('Missing')),
                                                                   line.get('ref', line),
                                                                   repr(err)))
                else:
                    try:
                        line[rule] = conversion_rules[rule](line[rule])
                    except Exception as err:
                        raise except_osv(_('Invalid data'),
                                         _("Value %s of column %s is not valid."
                                           "\n Please check the line with ref %s:"
                                           "\n \n Detail: %s") % (line.get(rule, _('Missing')),
                                                                  rule,
                                                                  line.get('ref', line),
                                                                  repr(err)))
        return result_set

    def get_st_line_vals(self, line, *args, **kwargs):
        """
        This method must return a dict of vals that can be passed to create
        method of statement line in order to record it. It is the responsibility
        of every parser to give this dict of vals, so each one can implement his
        own way of recording the lines.
            :param:  line: a dict of vals that represent a line of result_row_list
            :return: dict of values to give to the create method of statement line,
                     it MUST contain at least:
                {
                    'name':value,
                    'date':value,
                    'amount':value,
                    'ref':value,
                    'label':value,
                }
        """
        amount_type = line.get('Transaction Amount Type', None)
        amount = line.get('Amount', 0.0)
        if not amount_type:
            raise except_osv(
                _('Invalid data'),
                _('Some of the "Transaction Amount Type" is empty!'))
        if amount_type == 'DR' and amount:
            #if the type is DR, the amount should be negative
            amount = float(amount) * -1
        date = line.get('Value Date', datetime.datetime.now().date())

        return {
            'name': line.get('Reference', line.get('ref', '/')),
            'date': date,
            'amount': float(amount),
            'ref': line.get('Narrative', '/'),
            'label': line.get('Reference', ''),
        }


class VisaFileParser(generic_file_parser.FileParser):
    '''this file has no header.
    I add the columns to the tmp file.
    '''
    def __init__(self, parse_name, ftype='csv', **kwags):
        super(self.__class__, self).__init__(parse_name, ftype=ftype, **kwags)
        self.conversion_dict = {
            'Visa Number': unicode,
            'Amount Type': unicode,
            'Amount': unicode,
            'Key Reference': unicode,
            'Date1': datetime.datetime,
            'Date2': datetime.datetime,
            'Reference1': unicode,
            'Reference2': unicode
        }
        self.keys_to_validate = self.conversion_dict.keys()

    @classmethod
    def parser_for(cls, parser_name):
        """
        Used by the new_bank_statement_parser class factory. Return true if
        the providen name is FCT_bank_statement_csv
        """
        return parser_name == ('Visa_bank_statement_csv')

    def _validate(self, *args, **kwargs):
        return True

    def _parse_csv(self):
        """
        :return: list of dict from csv file (line/rows)
        """
        #the number of columns.
        supposed_length = 8

        def _correct_line(line, supposed_length):
            #TODO be more pythonic
            '''if the line's columns is less than supposed_length,
                append comma to the end(not the end. the end is '\n').'''
            if line:
                length = len(line.split(','))
                if length > supposed_length + 1:
                    raise except_osv(_("Date format is not valid."),
                                     _("Too much columns, %d expected." % supposed_length))
                elif length == supposed_length + 1:
                    #delete the end comma
                    line = (line.find(',') != -1) and\
                        line[:line.rindex(',')] + '\n' or line
                else:
                    #if there is no \n in line.
                    if line.find('\n') == -1:
                        line += ',' * (supposed_length - length)
                    else:
                        #if the line has \n, append comma before '\n'
                        line = line[:line.rindex('\n')] + ',' * (
                            supposed_length - length) + '\n'
            return line

        csv_file = tempfile.NamedTemporaryFile()
        #write the title of the file.
        csv_file.write(
            u'''Visa Number,Amount Type,Amount,Key Reference,'''
            '''Date1,Date2,Reference1,Reference2\n''')
        csv_file.write(self.filebuffer)
        #correct the file, some of them may have less columns.
        csv_file.flush()
        corrected_file = tempfile.NamedTemporaryFile()
        with open(corrected_file.name, 'r+') as target_file:
            with open(csv_file.name, 'rU') as fobj:
                for line in fobj:
                    target_file.write(_correct_line(line, supposed_length))
                target_file.flush()
        with open(corrected_file.name, 'rU') as corrected_obj:
            reader = UnicodeDictReader(
                corrected_obj, fieldnames=self.fieldnames)
            return list(reader)

    def _from_csv(self, result_set, conversion_rules):
        """
        Handle the converstion from the dict and handle date format from
        an .csv file.
        rewrite this method and do the date converstion.
        """
        date_format = '%d/%M/%Y'
        for line in result_set:
            for rule in conversion_rules:
                if conversion_rules[rule] == datetime.datetime:
                    try:
                        date_string = line[rule].split(' ')[0]
                        date_string = datetime.datetime.strptime(
                            date_string,
                            date_format)
                        line[rule] = date_string.strftime('%Y-%m-%d')
                    except ValueError as err:
                        raise except_osv(_("Date format is not valid."),
                                         _(" It should be YYYY-MM-DD for column: %s"
                                           " value: %s \n \n"
                                           " \n Please check the line with ref: %s"
                                           " \n \n Detail: %s") % (rule,
                                                                   line.get(rule, _('Missing')),
                                                                   line.get('ref', line),
                                                                   repr(err)))
                else:
                    try:
                        line[rule] = conversion_rules[rule](line[rule])
                    except Exception as err:
                        raise except_osv(_('Invalid data'),
                                         _("Value %s of column %s is not valid."
                                           "\n Please check the line with ref %s:"
                                           "\n \n Detail: %s") % (line.get(rule, _('Missing')),
                                                                  rule,
                                                                  line.get('ref', line),
                                                                  repr(err)))
        return result_set

    def get_st_line_vals(self, line, *args, **kwargs):
        """
        This method must return a dict of vals that can be passed to create
        method of statement line in order to record it. It is the responsibility
        of every parser to give this dict of vals, so each one can implement his
        own way of recording the lines.
            :param:  line: a dict of vals that represent a line of result_row_list
            :return: dict of values to give to the create method of statement line,
                     it MUST contain at least:
                {
                    'name':value,
                    'date':value,
                    'amount':value,
                    'ref':value,
                    'label':value,
                }
        """
        amount_type = line.get('Amount Type', None)
        amount = line.get('Amount', 0.0)
        if not amount_type:
            raise except_osv(
                _('Invalid data'),
                _('Some of the "Amount Type (Debit/Credit)" is empty!'))
        if amount_type == 'D' and amount:
            #if the type is DR, the amount should be negative
            amount = float(amount) * -1
        #we use Date2 here.
        date = line.get('Date2', datetime.datetime.now().date())
        ref = line.get('Key Reference', '') +\
            (line.get(
                'Reference1', '') and ('-' + line.get('Reference1')) or '') +\
            (line.get(
                'Reference2', '') and ('-' + line.get('Reference2')) or '')
        return {
            'ref': ref,
            'date': date,
            'amount': float(amount),
            'name': line.get('Visa Number', '/'),
            'label': line.get('Key Reference', '/'),
        }


class TRNFileParser(generic_file_parser.FileParser):
    '''This is a class that parser TRN bank statement
    '''
    def __init__(self, parse_name, ftype='csv', **kwags):
        super(self.__class__, self).__init__(parse_name, ftype=ftype, **kwags)
        self.conversion_dict = {
            'Record Type': unicode,
            'CMS ID': unicode,
            'Account Number': unicode,
            'Amount': unicode,
            'Serial No': unicode,
            'Tran Code': unicode,
            'Particulars': unicode,
            'Code': unicode,
            'Reference': unicode,
            'Other Party': unicode,
            'Date': datetime.datetime,
            'Originator Bank/Branch': unicode
        }
        self.keys_to_validate = self.conversion_dict.keys()

    @classmethod
    def parser_for(cls, parser_name):
        """
        Used by the new_bank_statement_parser class factory. Return true if
        the providen name is FCT_bank_statement_csv
        """
        return parser_name == ('TRN_bank_statement_csv')

    def _validate(self, *args, **kwargs):
        return True

    def _from_csv(self, result_set, conversion_rules):
        """
        Handle the converstion from the dict and handle date format from
        an .csv file.
        rewrite this method and do the date converstion.
        """
        date_format = '%M/%d/%Y'
        for line in result_set:
            for rule in conversion_rules:
                if conversion_rules[rule] == datetime.datetime:
                    try:
                        date_string = line[rule].split(' ')[0]
                        date_string = datetime.datetime.strptime(
                            date_string,
                            date_format)
                        line[rule] = date_string.strftime('%Y-%m-%d')
                    except ValueError as err:
                        raise except_osv(_("Date format is not valid."),
                                         _(" It should be YYYY-MM-DD for column: %s"
                                           " value: %s \n \n"
                                           " \n Please check the line with ref: %s"
                                           " \n \n Detail: %s") % (rule,
                                                                   line.get(rule, _('Missing')),
                                                                   line.get('ref', line),
                                                                   repr(err)))
                else:
                    try:
                        line[rule] = conversion_rules[rule](line[rule])
                    except Exception as err:
                        raise except_osv(_('Invalid data'),
                                         _("Value %s of column %s is not valid."
                                           "\n Please check the line with ref %s:"
                                           "\n \n Detail: %s") % (line.get(rule, _('Missing')),
                                                                  rule,
                                                                  line.get('ref', line),
                                                                  repr(err)))
        return result_set

    def get_st_line_vals(self, line, *args, **kwargs):
        """
        This method must return a dict of vals that can be passed to create
        method of statement line in order to record it. It is the responsibility
        of every parser to give this dict of vals, so each one can implement his
        own way of recording the lines.
            :param:  line: a dict of vals that represent a line of result_row_list
            :return: dict of values to give to the create method of statement line,
                     it MUST contain at least:
                {
                    'name':value,
                    'date':value,
                    'amount':value,
                    'ref':value,
                    'label':value,
                }
        """
        amount = line.get('Amount', 0.0)

        ref = line.get('Particulars', '') +\
            (line.get(
                'Reference', '') and ('-' + line.get('Reference')) or '') +\
            (line.get(
                'Other Party', '') and ('-' + line.get('Other Party')) or '')
        return {
            'name': line.get('Account Number', line.get('ref', '/')),
            'date': line.get('Date', datetime.datetime.now().date()),
            'amount': float(amount),
            'ref': ref,
            'label': line.get('Code', ''),
        }


class TrademeFileParser(generic_file_parser.FileParser):
    '''This is a class that parser the following format csv:
    Date    Description Money In    Money Out   Balance Auction #   Purchase #
    SKU
        *****
        parse process:
            self._format(*args, **kwargs)
            self._pre(*args, **kwargs)   ----   "pre-treatment"
            self._parse(*args, **kwargs)
            self._validate(*args, **kwargs)
            self._post(*args, **kwargs)
    '''
    def __init__(self, parse_name, ftype='csv', **kwags):
        super(self.__class__, self).__init__(parse_name, ftype=ftype, **kwags)
        self.conversion_dict = {
            'Date': datetime.datetime,
            'Description': unicode,
            'Money In': unicode,
            'Money Out': unicode,
            'Balance': unicode,
            'Auction #': unicode,
            'Purchase #': unicode,
        }
        self.keys_to_validate = self.conversion_dict.keys()

    @classmethod
    def parser_for(cls, parser_name):
        """
        Used by the new_bank_statement_parser class factory. Return true if
        the providen name is FCT_bank_statement_csv
        """
        return parser_name == ('Trademe_bank_statement_csv')

    def _validate(self, *args, **kwargs):
        return super(self.__class__, self)._validate(*args, **kwargs)

    def _from_csv(self, result_set, conversion_rules):
        """
        Handle the converstion from the dict and handle date format from
        an .csv file.
        rewrite this method and do the date converstion.
        """
        #Apr 7 2014
        date_format = '%m %d %Y'
        month_map = {
            'Jan': '1', 'Feb': '2', 'Mar': '3', 'Apr': '4', 'May': '5',
            'Jun': '6', 'Jul': '7',
            'Aug': '8', 'Sep': '9',
            'Oct': '10', 'Nov': '11', 'Dec': '12'}
        for line in result_set:
            for rule in conversion_rules:
                if conversion_rules[rule] == datetime.datetime:
                    try:
                        date_string = line[rule].strip()
                        if date_string:
                            temp_date_list = date_string.split(' ')
                            # if len(temp_date_list[1]) <= 1:
                                #convert the date.
                                #tried this format '%b %d %Y', failed
                                #so have to do it in a dirty way.
                            if temp_date_list[0] in month_map.keys():
                                temp_date_list[0] = month_map.get(
                                    temp_date_list[0])
                            else:
                                raise except_osv(
                                    _("Date format is not valid."),
                                    _(" It should be YYYY-MM-DD for column: %s"
                                        " value: %s \n \n"
                                        " \n Please check the line with ref: %s"
                                        " \n \n Detail: %s") % (
                                        rule,
                                        line.get(rule, _('Missing')),
                                        line.get('ref', line),
                                        repr(err)))
                            date_string = ' '.join(temp_date_list)
                        date_string = datetime.datetime.strptime(
                            date_string,
                            date_format)
                        line[rule] = date_string.strftime('%Y-%m-%d')
                    except ValueError as err:
                        raise except_osv(_("Date format is not valid."),
                                         _(" It should be YYYY-MM-DD for column: %s"
                                           " value: %s \n \n"
                                           " \n Please check the line with ref: %s"
                                           " \n \n Detail: %s") % (rule,
                                                                   line.get(rule, _('Missing')),
                                                                   line.get('ref', line),
                                                                   repr(err)))
                else:
                    try:
                        line[rule] = conversion_rules[rule](line[rule])
                    except Exception as err:
                        raise except_osv(_('Invalid data'),
                                         _("Value %s of column %s is not valid."
                                           "\n Please check the line with ref %s:"
                                           "\n \n Detail: %s") % (line.get(rule, _('Missing')),
                                                                  rule,
                                                                  line.get('ref', line),
                                                                  repr(err)))
        return result_set

    def get_st_line_vals(self, line, *args, **kwargs):
        """
        This method must return a dict of vals that can be passed to create
        method of statement line in order to record it. It is the responsibility
        of every parser to give this dict of vals, so each one can implement his
        own way of recording the lines.
            :param:  line: a dict of vals that represent a line of result_row_list
            :return: dict of values to give to the create method of statement line,
                     it MUST contain at least:
                {
                    'name':value,
                    'date':value,
                    'amount':value,
                    'ref':value,
                    'label':value,
                }
        """
        #TODO not sure this is proper thing to do.
        if not line.get('Purchase #').strip():
            #ignore
            return {
                'name': '',
                'date': None,
                'amount': 0,
                'ref': '',
                'label': '',
            }
        #TODO take care of the negative?
        if 'Pay Now fee' in line.get('Description').strip():
            amount = float(line.get('Money Out', 0.0).strip()) * -1
        elif 'Sale of' in line.get('Description').strip():
            amount = float(line.get('Money In', 0.0).strip())
        date = line.get('Date', datetime.datetime.now().date())
        return {
            'name': line.get('Purchase #', line.get('ref', '/')).strip(),
            'date': date,
            'amount': amount,
            'ref': line.get(
                'Description', '/').strip() + line.get('SKU', '/').strip(),
            #'trademe' is for a reference to generate a new move lines.
            'label': line.get('Auction #', '').strip()
            + (('Pay Now fee' not in line.get(
                'Description')) and '/trademe#' or ''),
        }
