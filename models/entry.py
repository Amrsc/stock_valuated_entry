# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, date
from odoo.exceptions import UserError,ValidationError


class StockValuatedEntry(models.Model):
    _name = 'stock.valuated.entry'
    _description = u'Entrée stock valorisé'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name   = fields.Char(u'Numéro', default='/', readonly=1)
    date   = fields.Date('Date', required=1, default=date.today(), readonly=1, states={'draft': [('readonly', False)]})
    notes  = fields.Text('Notes', readonly=1, states={'draft': [('readonly', False)]})
    stock_ids = fields.One2many('stock.valuated.entry.line', 'entry_id', states={'done': [('readonly', True)]})
    partner_id = fields.Many2one('res.partner', 'id', states={'done': [('readonly', True)]})
    company_id = fields.Many2one('res.company', string=u'Société', default=lambda self: self.env.company, states={'done': [('readonly', True)]})
    depot_id = fields.Many2one('stock.warehouse', string=u'Dépôt', required=1, states={'done': [('readonly', True)]})
    location_id = fields.Many2one('stock.location', string='Emplacement', required=1, states={'done': [('readonly', True)]})
    operation_id = fields.Many2one('stock.picking.type', string='Opération', required=1, states={'done': [('readonly', True)]})
    picking_id = fields.Many2one('stock.picking', string='Entrée stock')
    state  = fields.Selection([('draft', 'Nouveau'),
                               ('progress', 'En cours'),
                               ('done', 'Validée'),
                               ('cancel', 'Annulée'), ], string='Etat', default='draft')

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.valuated.entry') or '/'
        return super(StockValuatedEntry, self).create(vals)

    def unlink(self):
        if self.state != 'draft':
            raise UserError(_('Suppression non autorisée ! \n\n  L\'opération est déjà validée !'))
        else:
            return super(StockValuatedEntry, self).unlink()

    def action_cancel(self):
        self.state = 'cancel'

    def action_draft(self):
        self.state = 'draft'

    def create_picking(self):
        destination = self.location_id.id
        operation = self.operation_id.id
        source   = self.env['stock.location'].search([('usage', '=', 'supplier')])[0].id

        if destination == 70:
            picking = self.env['stock.picking'].create({
                'user_id': self.env.user.id,
                'state': 'draft',
                'partner_id' : self.partner_id.id ,
                'origin': self.name,
                'picking_type_id': operation,
                'move_type': 'direct',
                'company_id': self.company_id.id,
                'scheduled_date': self.date,
                'create_uid': self.env.user.id,
                'create_date': datetime.now(),
                'write_uid': self.env.user.id,
                'write_date': datetime.now(),
                'printed': False,
                'location_id': source,
                'location_dest_id': destination,
            })
        else :
            picking = self.env['stock.picking'].create({
                'user_id': self.env.user.id,
                'state': 'draft',
                'origin': self.name,
                'partner_id': self.partner_id.id,
                'picking_type_id': operation,
                'move_type': 'direct',
                'company_id': self.company_id.id,
                'scheduled_date': self.date,
                'create_uid': self.env.user.id,
                'create_date': datetime.now(),
                'write_uid': self.env.user.id,
                'write_date': datetime.now(),
                'printed': False,
                'location_id': source,
                'location_dest_id': destination,
            })

        self.picking_id = picking.id

        for rec in self.stock_ids:
            move = self.env['stock.move'].create({
                'picking_id'      : picking.id,
                'product_id'      : rec.product_id.id,
                'name'            : rec.name.name,
                'origin'          : self.name,
                'product_uom'     : rec.uom_id.id,
                'product_uom_qty' : rec.qty,
                'procure_method'  : 'make_to_stock',
                'picking_type_id' : operation,
                'sequence'        : 10,
                'company_id'      : self.company_id.id,
                'state'           : 'waiting',
                'location_id'     : source,
                'location_dest_id': destination,
                'date'            : datetime.now(),
                'scrapped'        : False,
            })
            lot_id = self.create_lot(rec)
            self.env['stock.move.line'].create({
                'move_id': move.id,
                'picking_id': picking.id,
                'company_id': self.company_id.id,
                'product_id': rec.product_id.id,
                'product_uom_id': rec.uom_id.id,
                'product_uom_qty': 0,
                'qty_done': rec.qty,
                'lot_id': lot_id.id,
                'date': datetime.now(),
                'location_id': source,
                'location_dest_id': destination,
                'state': 'draft',
                'reference': picking.name,
                'expiration_date': lot_id.expiration_date,
                'currency_id': self.company_id.currency_id.id,
                'price_unit': rec.price_unit,
                'price_ppa': rec.price_ppa,
                'price_grossiste': rec.price_grossiste,
            })
        picking.action_assign()
        if picking.state == 'assigned':
            picking.button_validate()
            if picking.state == 'done':
                self.action_valorisations()
                self.state = 'done'
            else:
                self.state = 'progress'
        else:
            self.state = 'progress'


    def create_lot(self, rec):
        produit = rec.name
        if produit.prix_fixe:
            produit.list_price = rec.price_unit
            produit.price_ppa = rec.price_ppa
            produit.price_grossiste = rec.price_grossiste

        # creation ou selection du lot
        lot_search = self.env['stock.production.lot'].search([('id', '=', rec.num_lot.id), ('product_id', '=', rec.product_id.id)])
        if lot_search.exists():
            return lot_search[0]
        else:
            return self.env['stock.production.lot'].create({
                'name': rec.num_lot,
                'ref': '',
                'product_id': rec.product_id.id,
                'product_uom_id': rec.uom_id.id,
                'note': 'Créé suite a l\'insertion du stock de démarrage',
                'company_id': self.company_id.id,
                'expiration_date': rec.date_peremption,
                'currency_id': self.company_id.currency_id.id,
                'price_unit': rec.price_unit,
                'price_ppa': rec.price_ppa,
                'price_grossiste': rec.price_grossiste,
            })

    def action_valorisations(self):

        for rec in self.stock_ids:

            lot = self.env['stock.production.lot'].search([('id', '=', rec.num_lot.id), ('product_id', '=', rec.product_id.id)])
            # valorisation
            if not lot.exists():
                raise UserError(_(u'Lot non existant'))
            else:
                layer_search = self.env['stock.valuation.layer'].search([('lot_id', '=', lot.id), ('product_id', '=', rec.product_id.id), ('quantity', '=', rec.qty)])

                if layer_search.exists():
                    for lay in layer_search:
                        lay.unit_cost = rec.valeur
                        lay.value = lay.quantity * rec.valeur
                        lay.remaining_value = lay.quantity * rec.valeur
                        # pièce comptable
                        qty = abs(lay.quantity)
                        account_move_id = self.env['account.move'].browse(lay.account_move_id.id)
                        if account_move_id:
                            account_move_id.amount_total_signed = qty * rec.valeur
                            for ecr in account_move_id.line_ids:
                                req_client = "update account_move_line set debit=%s, credit=%s, balance=%s, amount_currency=%s where id=%s;"
                                if ecr.credit > 0:
                                    param = (0.0, qty * rec.valeur, -1 * qty * rec.valeur, -1 * qty * rec.valeur, ecr.id)
                                else:
                                    param = (qty * rec.valeur, 0.0, qty * rec.valeur, qty * rec.valeur, ecr.id)

                                self._cr.execute(req_client, param, )

    def action_validation(self):
        if self.picking_id and self.picking_id.state == 'done':
            self.action_valorisations()
        else:
            raise UserError(_(u'Veuillez d\'abord valider manuellement l\'entrée en stock'))


class StockValuatedEntryLine(models.Model):
    _name = 'stock.valuated.entry.line'
    _description = u'Ligne entrée stock a importer'

    @api.depends('name')
    def _get_product(self):
        for rec in self:
            rec.product_id = self.env['product.product'].search([('product_tmpl_id', '=', rec.name.id), ('default_code', '=', rec.name.default_code)])[0].id



    name            = fields.Many2one('product.template', string='Produit', required=True)
    product_id      = fields.Many2one('product.product', compute=_get_product)
    purchase_ok     = fields.Boolean(related='name.purchase_ok')
    num_lot         = fields.Many2one('stock.production.lot', string='N° Lot' , required=True)
    qty             = fields.Float(u'Quantité', required=True)
    qty_existante   = fields.Float(u'Quantité existante')
    uom_id          = fields.Many2one(related='name.uom_id', string=u'UM')
    valeur          = fields.Float('Cout unitaire', required=True)
    date_peremption = fields.Date('Date péremption')
    entry_id   = fields.Many2one('stock.valuated.entry', string='inventaire')
    price_ppa       = fields.Float('PPA')
    price_unit      = fields.Float('Vente')
    price_grossiste = fields.Float('Grossite')

    @api.onchange('name')
    def onchange_product(self):
        for rec in self:
            if rec.name.prix_fixe:
                rec.price_unit = rec.name.list_price
                rec.price_ppa = rec.name.price_ppa
                rec.price_grossiste = rec.name.price_grossiste
            lot_ids = self.env['stock.production.lot'].search([('product_id.name', '=', rec.name.name)])
            print (lot_ids.ids)
            rec.num_lot = None
            rec.date_peremption = None
            return {'domain': {'num_lot': [('id', 'in', lot_ids.ids)]}}

    @api.onchange('num_lot')
    def onchange_num_lot(self):
        for rec in self:
            if rec.num_lot and rec.product_id:
                lot_cost = self.env['stock.valuation.layer'].search(  [('product_id.id', '=', rec.product_id.id), ('lot_id', '=', rec.num_lot.id)], limit=1, order="id desc")
                rec.valeur = lot_cost.unit_cost
                lot_date = self.env['stock.production.lot'].search( [('product_id.id', '=', rec.product_id.id), ('id', '=', rec.num_lot.id)])
                rec.date_peremption = lot_date.expiration_date