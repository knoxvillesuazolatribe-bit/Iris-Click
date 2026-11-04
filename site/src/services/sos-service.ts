import { appClient } from '@/api/app-client'
import {
  sosActivationSchema,
  sosContactSchema,
  sosOverviewSchema,
  type SosContactForm,
} from '@/validators/sos-validator'

const toBody = (form: SosContactForm) => ({
  contact_name: form.contact_name,
  contact_number: form.contact_number || null,
  email_address: form.email_address || null,
  relationship: form.relationship || null,
})

/** Emergency SOS; every call needs a signed-in assistive user. */
export const sosService = {
  getOverview: () => appClient.get('/me/sos').then((r) => sosOverviewSchema.parse(r.data)),
  addContact: (form: SosContactForm) =>
    appClient.post('/me/sos/contacts', toBody(form)).then((r) => sosContactSchema.parse(r.data)),
  updateContact: (id: number, form: SosContactForm) =>
    appClient.put(`/me/sos/contacts/${id}`, toBody(form)).then((r) => sosContactSchema.parse(r.data)),
  deleteContact: (id: number) => appClient.delete(`/me/sos/contacts/${id}`).then(() => undefined),
  activate: (activationId: string) =>
    appClient
      .post('/me/sos/activate', { activation_id: activationId })
      .then((r) => sosActivationSchema.parse(r.data)),
  getActivation: (activationId: string) =>
    appClient.get(`/me/sos/activations/${activationId}`).then((r) => sosActivationSchema.parse(r.data)),
  cancel: () => appClient.post('/me/sos/cancel').then(() => undefined),
}
