import streamlit as st
from openai import OpenAI
from openai import AssistantEventHandler
from typing_extensions import override
import os
import re
import pandas as pd
import PyPDF2
import io
try:
  from tokens import openai_key
except ImportError:
  openai_key = os.getenv('OPENAI_API_KEY')

class EventHandler(AssistantEventHandler):
    @override    
    def on_text_created(self, text) -> None:
        print(f"\nassistant > ", end="", flush=True)
    @override     
    def on_text_delta(self, delta, snapshot):
        print(delta.value, end="", flush=True)
        
def on_tool_call_created(self, tool_call):
  print(f"\nassistant > {tool_call.type}\n", flush=True)

def on_tool_call_delta(self, delta, snapshot):
  if delta.type == 'code_interpreter':
    if delta.code_interpreter.input:
      print(delta.code_interpreter.input, end="", flush=True)
    if delta.code_interpreter.outputs:
      print(f"\n\noutput >", flush=True)
      for output in delta.code_interpreter.outputs:
        if output.type == "logs":
          print(f"\n{output.logs}", flush=True)

def extract_text_from_pdf(pdf_file):
    reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

def process_invoice_with_ai(client, pdf_text):
    thread = client.beta.threads.create()
    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=f"""Extraé la siguiente información de esta factura en formato JSON: 
        {{'Fecha': '...', 'Número de Factura': '...', 'CUIT Emisor': '...', 
        'Cliente': '...', 'Importe Total': '...', 'IVA': '...', 'Detalle de Productos': '...'}}
        
        El texto de la factura es: 
        {pdf_text}"""
    )
    
    with client.beta.threads.runs.stream(
        thread_id=thread.id,
        assistant_id='asst_nnDTLYK0nrjuIBJCdscnA6vb',
        event_handler=EventHandler()) as stream:
            stream.until_done()
            bot_response = stream.get_final_messages()
            bot_reply = bot_response[0].content[0].text.value
            bot_reply = re.sub(r"【.*?】", "", bot_reply)
    
    return bot_reply

# Configuración inicial
col_title, col_logo = st.columns([5, 1])
with col_title:
  st.title("DASSA Bot - Procesador de Facturas")
with col_logo:
  st.image('logo.png')

client = OpenAI(
    api_key=openai_key)

# Inicializar variables de sesión
if 'processed_invoices' not in st.session_state:
    st.session_state.processed_invoices = []
    
if 'conversation_started' not in st.session_state:
    st.session_state.conversation_started = False
    
if 'asking_for_more' not in st.session_state:
    st.session_state.asking_for_more = False
    
if 'finished' not in st.session_state:
    st.session_state.finished = False

# Mostrar mensajes de chat anteriores
if 'messages' not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "¡Hola! Soy DASSA-Bot. ¿Deseas procesar una factura en PDF? 🤖", "avatar": "avatar.png"}
    ]

for message in st.session_state.messages:
    st.chat_message(message["role"], avatar=message.get("avatar")).write(message["content"])

# Entrada del usuario
user_input = st.chat_input("Ingresa tu mensaje...")

# Procesar la entrada del usuario
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)
    
    if not st.session_state.conversation_started:
        st.session_state.conversation_started = True
        response = "Perfecto, por favor sube un archivo PDF de factura para procesar."
        st.session_state.messages.append({"role": "assistant", "content": response, "avatar": "avatar.png"})
        st.chat_message("assistant", avatar="avatar.png").write(response)
        
    elif st.session_state.asking_for_more:
        if any(word in user_input.lower() for word in ["sí", "si", "claro", "ok", "otra", "más"]):
            response = "Excelente, por favor sube otra factura."
            st.session_state.asking_for_more = False
            st.session_state.messages.append({"role": "assistant", "content": response, "avatar": "avatar.png"})
            st.chat_message("assistant", avatar="avatar.png").write(response)
        else:
            st.session_state.finished = True
            
            # Crear DataFrame y archivo Excel
            if st.session_state.processed_invoices:
                df = pd.DataFrame(st.session_state.processed_invoices)
                
                # Crear buffer de bytes para el archivo Excel
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Facturas')
                excel_data = excel_buffer.getvalue()
                
                # Mostrar enlace de descarga
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": "Aquí está el archivo Excel con todas las facturas procesadas:", 
                    "avatar": "avatar.png"
                })
                st.chat_message("assistant", avatar="avatar.png").write("Aquí está el archivo Excel con todas las facturas procesadas:")
                
                # Mostrar DataFrame en chat
                st.dataframe(df)
                
                # Enlace de descarga
                st.download_button(
                    label="Descargar Excel de Facturas",
                    data=excel_data,
                    file_name="facturas_procesadas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                response = "No se procesaron facturas. ¿Deseas intentar de nuevo?"
                st.session_state.messages.append({"role": "assistant", "content": response, "avatar": "avatar.png"})
                st.chat_message("assistant", avatar="avatar.png").write(response)
                st.session_state.conversation_started = False
                st.session_state.asking_for_more = False
                st.session_state.finished = False
    else:
        try:
            thread = client.beta.threads.create()
            message = client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=user_input
            )
            with client.beta.threads.runs.stream(
                thread_id=thread.id,
                assistant_id='asst_nnDTLYK0nrjuIBJCdscnA6vb',
                event_handler=EventHandler()) as stream:
                    stream.until_done()
                    bot_response = stream.get_final_messages()
                    bot_reply = bot_response[0].content[0].text.value
                    bot_reply = re.sub(r"【.*?】", "", bot_reply)
            
            st.session_state.messages.append({"role": "assistant", "content": bot_reply, "avatar": "avatar.png"})
            st.chat_message("assistant", avatar="avatar.png").write(bot_reply)
        except Exception as e:
            st.error(f"Error: {e}")
            
# Subida de archivos
if st.session_state.conversation_started and not st.session_state.asking_for_more and not st.session_state.finished:
    pdf_file = st.file_uploader("Sube una factura en PDF", type=["pdf"], key=f"pdf_uploader_{len(st.session_state.processed_invoices)}")
    
    if pdf_file is not None:
        with st.spinner("Procesando factura..."):
            # Extraer texto del PDF
            pdf_text = extract_text_from_pdf(pdf_file)
            
            # Procesar la factura con OpenAI
            invoice_data_json = process_invoice_with_ai(client, pdf_text)
            
            # Mostrar resultados
            st.session_state.messages.append({
                "role": "assistant", 
                "content": f"He analizado la factura:\n\n{invoice_data_json}\n\n¿Deseas agregar otra factura?", 
                "avatar": "avatar.png"
            })
            st.chat_message("assistant", avatar="avatar.png").write(f"He analizado la factura:\n\n{invoice_data_json}\n\n¿Deseas agregar otra factura?")
            
            # Agregar a lista de facturas procesadas
            try:
                # Intentar extraer el JSON de la respuesta del bot (puede requerir ajustes)
                import json
                # Encontrar el bloque JSON en el texto
                json_match = re.search(r'\{.*\}', invoice_data_json, re.DOTALL)
                if json_match:
                    invoice_dict = json.loads(json_match.group())
                    st.session_state.processed_invoices.append(invoice_dict)
                else:
                    # Plan B: parsear manualmente si es necesario
                    st.session_state.processed_invoices.append({"Datos": invoice_data_json})
            except Exception as e:
                st.warning(f"No se pudo extraer JSON estructurado: {e}")
                st.session_state.processed_invoices.append({"Datos": invoice_data_json})
            
            st.session_state.asking_for_more = True

