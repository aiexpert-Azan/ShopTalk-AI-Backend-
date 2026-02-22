from twilio.rest import Client

account_sid = 'ACe5c13671a538aff4396f6fd0b772f201'
auth_token = '097f6740c0f56046336ff7440f418f34'
client = Client(account_sid, auth_token)

message = client.messages.create(
  from_='whatsapp:+14155238886',
  content_sid='HXb5b62575e6e4ff6129ad7c8efe1f983e',
  content_variables='{"1":"12/1","2":"3pm"}',
  to='whatsapp:+923269157985'
)

print(message.sid)
