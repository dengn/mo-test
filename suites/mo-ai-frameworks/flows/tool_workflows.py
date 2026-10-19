"""Real tool/SDK workflows moved from the verified compatibility prototypes."""
import json,asyncio
from shared import query
scenarios=[("a",[1]),("b",[2]),("missing",[]),("a' OR 1=1 --",[])]

def make_lookup(cfg,trace):
 def lookup(tenant:str)->str:
  """Retrieve knowledge belonging to the exact tenant identifier.

  Args:
      tenant: Tenant identifier used as a bound SQL parameter.
  """
  rows=query(cfg,'SELECT id,tenant,content FROM knowledge WHERE tenant=%s ORDER BY id',(tenant,))
  result=[dict(id=r[0],tenant=r[1],content=r[2]) for r in rows];trace.append((tenant,result))
  return json.dumps(result,ensure_ascii=False)
 return lookup

def smolagents_loop(cfg):
 from smolagents import Tool,ToolCallingAgent,Model
 from smolagents.models import ChatMessage,ChatMessageToolCall,ChatMessageToolCallFunction,MessageRole
 trace=[];lookup=make_lookup(cfg,trace)
 class Retrieve(Tool):
  name='retrieve';description='Retrieve tenant-specific MatrixOne SQL knowledge'
  inputs={'tenant':{'type':'string','description':'Tenant identifier'}};output_type='string'
  def forward(self,tenant:str)->str:return lookup(tenant)
 class FixtureModel(Model):
  def __init__(self,tenant):super().__init__(model_id='fixture');self.tenant=tenant;self.calls=0;self.observed=None
  def generate(self,messages,**kwargs):
   self.calls+=1
   if self.calls==1:name='retrieve';arguments={'tenant':self.tenant}
   else:self.observed=messages;name='final_answer';arguments={'answer':'done'}
   return ChatMessage(role=MessageRole.ASSISTANT,tool_calls=[ChatMessageToolCall(function=ChatMessageToolCallFunction(name=name,arguments=arguments),id='call_'+str(self.calls),type='function')])
 for tenant,ids in scenarios:
  model=FixtureModel(tenant);agent=ToolCallingAgent(tools=[Retrieve()],model=model,max_steps=3,verbosity_level=0)
  assert agent.run('Retrieve the requested tenant and finish')=='done'
  assert model.calls==2 and model.observed is not None
  assert [r['id'] for r in trace[-1][1]]==ids and trace[-1][0]==tenant
  assert json.dumps(trace[-1][1],ensure_ascii=False) in str(model.observed),'Database observation missing from next model input'
 return 'actual ToolCallingAgent.run -> native Tool -> bound SQL -> observation -> final_answer; four tenant scenarios; scripted Model only'

def dspy_loop(cfg):
 import dspy
 from dspy.utils.dummies import DummyLM
 trace=[];lookup=make_lookup(cfg,trace)
 for tenant,ids in scenarios:
  answers=[{'next_thought':'Read database','next_tool_name':'lookup','next_tool_args':{'tenant':tenant}}, {'next_thought':'Observed database result','next_tool_name':'finish','next_tool_args':{}}, {'reasoning':'Fixture completion','answer':'done'}]
  react=dspy.ReAct('question -> answer',tools=[dspy.Tool(lookup)],max_iters=3)
  with dspy.context(lm=DummyLM(answers=answers)):prediction=react(question='Retrieve the requested tenant')
  assert prediction.answer=='done'
  assert [r['id'] for r in trace[-1][1]]==ids and trace[-1][0]==tenant
  assert json.loads(prediction.trajectory['observation_0'])==trace[-1][1]
 return 'actual ReAct/DummyLM -> native Tool -> SQL -> trajectory observation -> extraction; four tenant scenarios; no optimization/real inference certification'

def litellm_callbacks(cfg):
 import litellm
 from adapters.litellm_logger import MatrixOneLiteLLMLogger
 logger=MatrixOneLiteLLMLogger(cfg);previous=list(litellm.callbacks);litellm.callbacks=[logger]
 try:
  for tenant in ['a','b']:
   logger.completed.clear()
   response=litellm.completion(model='gpt-4o-mini',messages=[{'role':'user','content':'fixture'}],mock_response='完成 '+tenant,metadata={'tenant':tenant})
   assert response.choices[0].message.content=='完成 '+tenant
   assert logger.completed.wait(10),'Native synchronous success callback did not finish'
   assert not logger.errors,logger.errors
   events=logger.list_events(tenant);assert len(events)==1
   assert events[0]['id']==response.id and events[0]['payload']['choices'][0]['message']['content']=='完成 '+tenant
   logger.log_success_event(*logger.last_event);assert len(logger.list_events(tenant))==1
  reopened=MatrixOneLiteLLMLogger(cfg)
  assert len(reopened.list_events('a'))==len(reopened.list_events('b'))==1
  assert reopened.list_events("a' OR 1=1 --")==[]
  async def async_request():
   logger.completed.clear()
   response=await litellm.acompletion(model='gpt-4o-mini',messages=[{'role':'user','content':'fixture'}],mock_response='异步',metadata={'tenant':'async'})
   assert await asyncio.to_thread(logger.completed.wait,10),'Native async success callback did not finish'
   assert not logger.errors,logger.errors
   assert logger.list_events('async')[0]['id']==response.id
  asyncio.run(async_request())
  return 'native completion/acompletion success callbacks -> selected response JSON in SQL; tenant isolation, reopen, duplicate-event replay; mock_response only; no Prisma/proxy migration'
 finally:litellm.callbacks=previous
