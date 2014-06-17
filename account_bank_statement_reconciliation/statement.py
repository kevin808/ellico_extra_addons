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
import sys
import datetime
import traceback
from openerp.osv import orm, fields, osv
from openerp.addons.account_statement_base_import.parser.parser\
    import new_bank_statement_parser
from openerp.tools.config import config
from tools.translate import _


class ErrorTooManyPartner(Exception):
    """
    New Exception definition that is raised when more
    than one partner is matched by
    the completion rule.
    """
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

    def __repr__(self):
        return repr(self.value)


class AccountStatementProfile(orm.Model):
    _inherit = 'account.statement.profile'

    def get_import_type_selection(self, cr, uid, context=None):
        res = super(AccountStatementProfile, self).get_import_type_selection(
            cr, uid, context=context)
        new_methods = [
            ('Visa_bank_statement_csv', 'Visa bank statement csv import'),
            ('FCT_bank_statement_csv', 'FCT bank statement csv import'),
            ('TRN_bank_statement_csv', 'TRN bank statement csv import'),
            ('Trademe_bank_statement_csv', 'Trademe bank statement csv import')
        ]
        res += new_methods
        return res

    def statement_import(
            self, cr, uid, ids,
            profile_id, file_stream, ftype="csv", context=None):
        """
        Create a bank statement with the given profile and parser.
        It will fullfill the bank statement
        with the values of the file providen, but will not complete data
        (like finding the partner, or
        the right account). This will be done in a second step
        with the completion rules.

        :param int/long profile_id: ID of the profile used to import the file
        :param filebuffer file_stream: binary of the providen file
        :param char: ftype represent the file exstension (csv by default)
        :return: ID of the created account.bank.statemênt

        #rewrite this method just for Trademe import and ingore the method
            returned by method get_st_line_vals, if it is None.
        """
        statement_obj = self.pool.get('account.bank.statement')
        statement_line_obj = self.pool.get('account.bank.statement.line')
        attachment_obj = self.pool.get('ir.attachment')
        prof_obj = self.pool.get("account.statement.profile")
        if not profile_id:
            raise osv.except_osv(_("No Profile!"),
                                 _("You must provide a valid "
                                   "profile to import a bank statement!"))
        prof = prof_obj.browse(cr, uid, profile_id, context=context)

        parser = new_bank_statement_parser(prof.import_type, ftype=ftype)
        result_row_list = parser.parse(file_stream)
        # Check all key are present in account.bank.statement.line!!
        if not result_row_list:
            raise osv.except_osv(_("Nothing to import"),
                                 _("The file is empty"))
        parsed_cols = parser.get_st_line_vals(result_row_list[0]).keys()
        if parsed_cols:
            for col in parsed_cols:
                if col not in statement_line_obj._columns:
                    raise osv.except_osv(
                        _("Missing column!"),
                        _("Column %s you try to import is not "
                          "present in the bank statement line!") % col)
            statement_vals = self.prepare_statement_vals(
                cr, uid, prof.id, result_row_list, parser, context)
            statement_id = statement_obj.create(cr, uid,
                                                statement_vals,
                                                context=context)

            if prof.receivable_account_id:
                account_receivable = account_payable =\
                    prof.receivable_account_id.id
            else:
                account_receivable, account_payable =\
                    statement_obj.get_default_pay_receiv_accounts(
                        cr, uid, context)
            try:
                # Record every line in the bank statement
                statement_store = []
                for line in result_row_list:
                    #ignore
                    #just for Trademe bank statment,
                    # might have to ignore some lines.
                    if ('Purchase #' in line.keys()) and (not line.get(
                            'Purchase #', '')):
                        continue
                    parser_vals = parser.get_st_line_vals(line)
                    values = self.prepare_statement_lines_vals(
                        cr, uid, parser_vals, account_payable,
                        account_receivable, statement_id,
                        context)
                    statement_store.append(values)
                # Hack to bypass ORM poor perfomance. Sob...
                statement_line_obj._insert_lines(
                    cr, uid, statement_store, context=context)

                self._write_extra_statement_lines(
                    cr, uid, parser, result_row_list,
                    prof, statement_id, context)
                # Trigger store field computation if someone has better idea
                start_bal = statement_obj.read(
                    cr, uid, statement_id, ['balance_start'], context=context)
                start_bal = start_bal['balance_start']
                statement_obj.write(
                    cr, uid, [statement_id], {'balance_start': start_bal})

                attachment_data = {
                    'name': 'statement file',
                    'datas': file_stream,
                    'datas_fname': "%s.%s" % (
                        datetime.datetime.now().date(), ftype),
                    'res_model': 'account.bank.statement',
                    'res_id': statement_id,
                }
                attachment_obj.create(
                    cr, uid, attachment_data, context=context)

                # If user ask to launch completion at end of import, do it!
                if prof.launch_import_completion:
                    statement_obj.button_auto_completion(
                        cr, uid, [statement_id], context)

                # Write the needed log infos on profile
                self.write_logs_after_import(cr, uid, prof.id,
                                             statement_id,
                                             len(result_row_list),
                                             context)

            except Exception:
                error_type, error_value, trbk = sys.exc_info()
                st = "Error: %s\nDescription: %s\nTraceback:" % (
                    error_type.__name__, error_value)
                st += ''.join(traceback.format_tb(trbk, 30))
                #TODO we should catch correctly the exception with a python
                #Exception and only re-catch some special exception.
                #For now we avoid re-catching error in debug mode
                if config['debug_mode']:
                    raise
                raise osv.except_osv(
                    _("Statement import error"),
                    _("The statement cannot be created: %s") % st)
            return statement_id
        #default we return the
        return False


class account_bank_statement_line(orm.Model):
    _inherit = 'account.bank.statement.line'
    _columns = {
        #just to change the size of the ref.
        'ref': fields.char('Reference', size=250, required=True)
    }


#the rule to get trademe account.
class AccountStatementCompletionRule(orm.Model):
    _name = 'account.statement.completion.rule'
    _inherit = "account.statement.completion.rule"

    def _get_functions(self, cr, uid, context=None):
        """
        List of available methods for rules.
        """
        #('get_from_ref_and_invoice', 'From line reference
                #(based on customer invoice number)'),
        #('get_from_ref_and_supplier_invoice', 'From line reference
            #(based on supplier invoice number)'),
        #('get_from_label_and_partner_field', 'From line label
            #(based on partner field)'),
        #('get_from_label_and_partner_name', 'From line label
            #(based on partner name)')
        res = super(AccountStatementCompletionRule, self)._get_functions(
            cr, uid, context=context)
        res.append(
            ('take_as_commission_for_trademe', 'Trademe commission (fee)'))
        return res

    _columns = {
        'function_to_call': fields.selection(_get_functions, 'Method'),
    }

    def take_as_commission_for_trademe(self, cr, uid, st_line, context=None):
        '''this method is for trademe bank statment, find the partner and
        account the trademe fee (commission)
        st_line:
        'account_id': (45, u'120000 Creditors'),
         'additionnal_bank_fields': {u'label': u'713265510'},
         'already_completed': False,
         'amount': -5.93,
         'amount_reconciled': 0.0,
         'analytic_account_id': False,
         'company_id': (1, u'Your Company'),
         'date': '2014-04-06',
         'id': 526,
         'journal_id': (20, u'Bank (EUR)'),
         'label': u'713265510',
         'master_account_id': False,
         'move_ids': [],
         'name': u'P107944811',
         'note': False,
         'partner_id': False,
         'period_id': (4, u'X 04/2014'),
         'profile_id': 6,
         'ref': u"Pay Now fee on 'Chicken Coop Hen Cage House Ru...'",
         'sequence': 527,
         'statement_id': (37, u'/'),
         'type': u'general',
         'voucher_id': False
        '''
        profile_obj = self.pool.get('account.statement.profile')
        so_obj = self.pool.get('sale.order')
        st_obj = self.pool.get('account.bank.statement.line')
        res = {}
        #find partner_id
        so_name = st_line.get('name', '')
        partner_ids = []
        if so_name:
            #TODO can we search only SO ?
            so_ids = so_obj.search(
                cr, uid, [('client_order_ref', 'like', so_name)])
            for so in so_obj.browse(cr, uid, so_ids):
                if so.partner_invoice_id and\
                        (so.partner_invoice_id.id not in partner_ids):
                    partner_ids.append(so.partner_invoice_id.id)
                #if we don't get the partner_invoice_id we get the partner_id.
                elif so.partner_id.id not in partner_ids:
                    partner_ids.append(so.partner_id.id)
            if len(partner_ids) > 1:
                raise ErrorTooManyPartner(
                    _('order whose client ref is "%s" '
                        'has more than one partner.') %
                    (st_line['name']))
        if partner_ids:
            st_vals = st_obj.get_values_for_line(
                cr,
                uid,
                profile_id=st_line['profile_id'],
                master_account_id=st_line['master_account_id'],
                partner_id=partner_ids and partner_ids[0],
                line_type=False,
                amount=st_line['amount'] if st_line['amount'] else 0.0,
                context=context)
            res.update(st_vals)
            res['partner_id'] = partner_ids and partner_ids[0] or False
            #Pay Now fee
            if ('Pay Now fee' in st_line.get('ref', '')) and st_line.get(
                    'profile_id', False):
                profile_bro = profile_obj.browse(
                    cr, uid, st_line.get('profile_id'), context=context)
                commission_account_id = profile_bro and\
                    profile_bro.commission_account_id.id or False
                res['account_id'] = commission_account_id
        return res


class AccountBankStatement(orm.Model):
    """
    We improve the bank statement class mostly for :
    - create extra move lines from AR to AR prepayment account.
        for trademe bank statement.
    Please note that:
        new move lines are only created
     """

    _inherit = "account.bank.statement"

    def _if_create_extra_move_lines(self, st_line):
        '''check if in the label we get 'trademe#'
            and partner has Prepayment account
            and prepayemnt account is not equals to AR account.
        '''
        if (not st_line) or (not st_line.partner_id):
            return False
        if not hasattr(st_line.partner_id, 'property_account_prereceivable'):
            return False
        if st_line.partner_id.property_account_prereceivable ==\
                st_line.partner_id.property_account_receivable:
            return False
        return bool('trademe#' in st_line.label)

    def create_move_from_st_line(
        self, cr, uid, st_line_id, company_currency_id,
            st_line_number, context=None):
        """Create the account move from the statement line.

           :param int/long st_line_id: ID of the account.bank.statement.
           line to create the move from.
           :param int/long company_currency_id:
           ID of the res.currency of the company
           :param char st_line_number: will be used as
           the name of the generated account move
           :return: ID of the account.move created

           override this method totally.
        """

        if context is None:
            context = {}
        res_currency_obj = self.pool.get('res.currency')
        account_move_obj = self.pool.get('account.move')
        account_move_line_obj = self.pool.get('account.move.line')
        account_bank_statement_line_obj = self.pool.get(
            'account.bank.statement.line')
        st_line = account_bank_statement_line_obj.browse(
            cr, uid, st_line_id, context=context)
        st = st_line.statement_id

        context.update({'date': st_line.date})

        move_vals = self._prepare_move(
            cr, uid, st_line, st_line_number, context=context)
        move_id = account_move_obj.create(cr, uid, move_vals, context=context)
        account_bank_statement_line_obj.write(cr, uid, [st_line.id], {
            'move_ids': [(4, move_id, False)]
        })
        torec = []
        acc_cur = (
            (st_line.amount <= 0) and
            st.journal_id.default_debit_account_id) or st_line.account_id

        context.update(
            {
                'res.currency.compute.account': acc_cur,
            })
        amount = res_currency_obj.compute(
            cr, uid, st.currency.id,
            company_currency_id, st_line.amount, context=context)

        bank_move_vals = self._prepare_bank_move_line(
            cr, uid, st_line, move_id, amount,
            company_currency_id, context=context)
        move_line_id = account_move_line_obj.create(
            cr, uid, bank_move_vals, context=context)
        torec.append(move_line_id)

        counterpart_move_vals = self._prepare_counterpart_move_line(
            cr, uid, st_line, move_id,
            amount, company_currency_id, context=context)
        account_move_line_obj.create(
            cr, uid, counterpart_move_vals, context=context)
#---
        #change begin
        #add extra move line if conditions satisfied [just for trademe BS].

        if self._if_create_extra_move_lines(st_line):
            debit_account = st_line.partner_id.property_account_prereceivable
            credit_account = st_line.partner_id.property_account_receivable
            bank_move_vals['account_id'] = credit_account.id
            extra_move_line_id = account_move_line_obj.create(
                cr, uid, bank_move_vals, context=context)
            counterpart_move_vals['account_id'] = debit_account.id
            account_move_line_obj.create(
                cr, uid, counterpart_move_vals, context=context)
            #create counterpart_move_line
            torec.append(extra_move_line_id)

        #change end
#---
        for line in account_move_line_obj.browse(
            cr, uid, [x.id for x in account_move_obj.browse(
                cr, uid, move_id,
                context=context).line_id],
                context=context):
            if line.state != 'valid':
                raise osv.except_osv(
                    _('Error!'),
                    _('Journal item "%s" is not valid.') % line.name)

        # Bank statements will not consider boolean on journal entry_posted
        account_move_obj.post(cr, uid, [move_id], context=context)
        return move_id
