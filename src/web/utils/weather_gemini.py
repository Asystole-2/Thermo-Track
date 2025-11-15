import os
import re
import json
import requests
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class WeatherAIAnalyzer:
    def __init__(self):
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.weather_api_key = os.getenv('OPENWEATHER_API_KEY')

        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel('gemini-pro')
        else:
            self.model = None

    def get_weather_data(self, city="Dublin", country_code="IE"):
        """Get current weather data from OpenWeather API"""
        print(f"DEBUG: Weather API Key exists: {bool(self.weather_api_key)}")
        print(
            f"DEBUG: Weather API Key: {self.weather_api_key[:10]}...{self.weather_api_key[-4:] if self.weather_api_key and len(self.weather_api_key) > 14 else 'N/A'}")

        if not self.weather_api_key:
            print("DEBUG: No weather API key found")
            return {
                'error': 'Weather API key not configured',
                'temperature': 15,
                'humidity': 75,
                'description': 'Partly cloudy',
                'wind_speed': 3.5
            }

        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city},{country_code}&appid={self.weather_api_key}&units=metric"
            print(f"DEBUG: API URL: {url.replace(self.weather_api_key, 'API_KEY_REDACTED')}")

            response = requests.get(url)
            print(f"DEBUG: Response status: {response.status_code}")
            print(f"DEBUG: Response content: {response.text[:200]}...")

            data = response.json()

            if response.status_code == 200:
                print("DEBUG: Successfully got weather data")
                return {
                    'temperature': data['main']['temp'],
                    'humidity': data['main']['humidity'],
                    'description': data['weather'][0]['description'],
                    'wind_speed': data['wind']['speed'],
                    'city': data['name'],
                    'condition': data['weather'][0]['main']  # Add this for condition
                }
            else:
                print(f"DEBUG: API Error: {data}")
                return {
                    'error': f"Weather data unavailable: {data.get('message', 'Unknown error')}",
                    'temperature': 15,
                    'humidity': 75,
                    'description': 'Partly cloudy',
                    'wind_speed': 3.5,
                    'condition': 'Cloudy'
                }

        except Exception as e:
            print(f"DEBUG: Exception occurred: {e}")
            return {
                'error': str(e),
                'temperature': 15,
                'humidity': 75,
                'description': 'Partly cloudy',
                'wind_speed': 3.5,
                'condition': 'Cloudy'
            }

    def generate_recommendations(self, room_data, weather_data, room_type="office"):
        """Generate AI-powered recommendations using Gemini"""
        if not self.model:
            return self._get_fallback_recommendations(room_data, weather_data)

        try:
            prompt = self._build_prompt(room_data, weather_data, room_type)
            response = self.model.generate_content(prompt)
            return self._parse_ai_response(response.text)

        except Exception as e:
            print(f"AI analysis failed: {e}")
            return self._get_fallback_recommendations(room_data, weather_data)

    def _build_prompt(self, room_data, weather_data, room_type):
        """Build the prompt for Gemini AI"""
        return f"""
        As an HVAC optimization expert, analyze these conditions and provide specific recommendations:

        ROOM CONDITIONS:
        - Temperature: {room_data.get('temperature', 'N/A')}°C
        - Humidity: {room_data.get('humidity', 'N/A')}%
        - Occupancy: {room_data.get('occupancy', 0)} people
        - Room Type: {room_type}

        EXTERNAL WEATHER:
        - Outside Temperature: {weather_data.get('temperature', 'N/A')}°C
        - Outside Humidity: {weather_data.get('humidity', 'N/A')}%
        - Conditions: {weather_data.get('description', 'N/A')}
        - Wind Speed: {weather_data.get('wind_speed', 'N/A')} m/s

        Please provide:
        1. HVAC SETTING RECOMMENDATION (target temperature)
        2. ENERGY EFFICIENCY TIPS
        3. COMFORT OPTIMIZATION
        4. VENTILATION ADVICE

        Format your response as a JSON-like structure with these sections.
        Keep recommendations practical and specific to the conditions.
        """

    def _parse_ai_response(self, response_text):
        """Robustly parse the AI response into structured data with multiple fallback strategies"""

        # Clean the response text first
        cleaned_text = self._clean_response_text(response_text)

        # Try multiple parsing strategies in order of reliability
        parsed_data = self._try_json_parsing(cleaned_text)
        if parsed_data:
            return self._validate_parsed_data(parsed_data, cleaned_text)

        parsed_data = self._try_structured_sections(cleaned_text)
        if parsed_data:
            return self._validate_parsed_data(parsed_data, cleaned_text)

        parsed_data = self._try_markdown_format(cleaned_text)
        if parsed_data:
            return self._validate_parsed_data(parsed_data, cleaned_text)

        # Fallback to intelligent extraction
        return self._intelligent_extraction_fallback(cleaned_text)

    def _clean_response_text(self, text):
        """Clean and normalize the AI response text"""
        # Remove code block markers
        text = re.sub(r'```(?:json)?\s*', '', text)
        text = re.sub(r'```\s*$', '', text)

        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = text.strip()

        return text

    def _try_json_parsing(self, text):
        """Attempt to parse JSON-formatted response"""
        try:
            # Look for JSON objects in the text
            json_match = re.search(r'\{[^{}]*"[^"]*"[^{}]*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                parsed = json.loads(json_str)

                # Map common field names to our expected structure
                return {
                    'ai_recommendation': parsed.get('summary', parsed.get('recommendation', text)),
                    'target_temperature': self._extract_temperature_from_dict(parsed),
                    'energy_tips': parsed.get('energy_tips', parsed.get('energy_efficiency', '')),
                    'comfort_advice': parsed.get('comfort_advice', parsed.get('comfort_optimization', '')),
                    'ventilation_advice': parsed.get('ventilation_advice', parsed.get('ventilation', '')),
                    'parsing_method': 'json'
                }
        except (json.JSONDecodeError, AttributeError):
            pass

        return None

    def _try_structured_sections(self, text):
        """Parse response with clear section headers"""
        sections = {
            'target_temperature': None,
            'energy_tips': [],
            'comfort_advice': [],
            'ventilation_advice': []
        }

        lines = text.split('\n')
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect section headers
            lower_line = line.lower()
            if any(keyword in lower_line for keyword in ['temperature', 'target', 'setpoint', 'recommended temp']):
                current_section = 'target_temperature'
                sections['target_temperature'] = self._extract_temperature(line)
            elif any(keyword in lower_line for keyword in ['energy', 'efficiency', 'saving', 'consumption']):
                current_section = 'energy_tips'
            elif any(keyword in lower_line for keyword in ['comfort', 'well-being', 'occupant', 'feel']):
                current_section = 'comfort_advice'
            elif any(keyword in lower_line for keyword in ['ventilation', 'airflow', 'fresh air', 'circulation']):
                current_section = 'ventilation_advice'
            elif current_section and current_section != 'target_temperature' and line:
                # Add content to current section
                if line and not line.endswith(':'):
                    sections[current_section].append(line)

        # Convert lists to strings
        return {
            'ai_recommendation': text,
            'target_temperature': sections['target_temperature'] or self._extract_temperature(text),
            'energy_tips': ' '.join(sections['energy_tips']) or self._extract_section(text, 'energy', 'efficiency'),
            'comfort_advice': ' '.join(sections['comfort_advice']) or self._extract_section(text, 'comfort',
                                                                                            'optimization'),
            'ventilation_advice': ' '.join(sections['ventilation_advice']) or self._extract_section(text, 'ventilation',
                                                                                                    'airflow'),
            'parsing_method': 'structured_sections'
        }

    def _try_markdown_format(self, text):
        """Parse markdown-style formatted response"""
        sections = {}

        # Look for markdown headers and their content
        headers = re.findall(r'^#+\s*(.+)$', text, re.MULTILINE)
        if headers:
            for header in headers:
                lower_header = header.lower()
                if any(keyword in lower_header for keyword in ['temperature', 'target']):
                    content = self._extract_markdown_section(text, header)
                    sections['target_temperature'] = self._extract_temperature(content)
                elif any(keyword in lower_header for keyword in ['energy', 'efficiency']):
                    sections['energy_tips'] = self._extract_markdown_section(text, header)
                elif any(keyword in lower_header for keyword in ['comfort']):
                    sections['comfort_advice'] = self._extract_markdown_section(text, header)
                elif any(keyword in lower_header for keyword in ['ventilation', 'airflow']):
                    sections['ventilation_advice'] = self._extract_markdown_section(text, header)

        if sections:
            return {
                'ai_recommendation': text,
                'target_temperature': sections.get('target_temperature', self._extract_temperature(text)),
                'energy_tips': sections.get('energy_tips', self._extract_section(text, 'energy', 'efficiency')),
                'comfort_advice': sections.get('comfort_advice',
                                               self._extract_section(text, 'comfort', 'optimization')),
                'ventilation_advice': sections.get('ventilation_advice',
                                                   self._extract_section(text, 'ventilation', 'airflow')),
                'parsing_method': 'markdown'
            }

        return None

    def _extract_markdown_section(self, text, header):
        """Extract content under a markdown header"""
        pattern = rf'#+\s*{re.escape(header)}\s*\n(.+?)(?=\n#+|\Z)'
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _intelligent_extraction_fallback(self, text):
        """Final fallback with intelligent pattern matching"""
        # Enhanced temperature extraction with context
        temp = self._extract_temperature_with_context(text)

        # Enhanced section extraction with better patterns
        energy_patterns = [
            r'(?:energy|efficiency)[^.]*?\.([^.]*\.){0,3}',
            r'reduce[^.]*?(energy|power|consumption)[^.]*?\.',
            r'saving[^.]*?(energy|cost)[^.]*?\.'
        ]

        comfort_patterns = [
            r'(?:comfort|well.being|occupant)[^.]*?\.([^.]*\.){0,3}',
            r'improve[^.]*?(comfort|feel|temperature)[^.]*?\.'
        ]

        ventilation_patterns = [
            r'(?:ventilation|airflow|fresh air)[^.]*?\.([^.]*\.){0,3}',
            r'open[^.]*?(window|vent)[^.]*?\.',
            r'circulat[^.]*?(air)[^.]*?\.'
        ]

        return {
            'ai_recommendation': text,
            'target_temperature': temp,
            'energy_tips': self._extract_with_patterns(text, energy_patterns, 'energy', 'efficiency'),
            'comfort_advice': self._extract_with_patterns(text, comfort_patterns, 'comfort', 'optimization'),
            'ventilation_advice': self._extract_with_patterns(text, ventilation_patterns, 'ventilation', 'airflow'),
            'parsing_method': 'intelligent_fallback'
        }

    def _extract_temperature_with_context(self, text):
        """Extract temperature with context awareness"""
        # Look for temperature in specific contexts
        patterns = [
            r'recommend[^.]*?(\d+)[°\s]*[Cc]',  # "recommend 22°C"
            r'target[^.]*?(\d+)[°\s]*[Cc]',  # "target temperature of 22°C"
            r'set[^.]*?(\d+)[°\s]*[Cc]',  # "set to 22°C"
            r'optimal[^.]*?(\d+)[°\s]*[Cc]',  # "optimal at 22°C"
            r'(\d+)[°\s]*[Cc][^.]*?recommend',  # "22°C is recommended"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                temp = int(match.group(1))
                if 16 <= temp <= 28:  # Reasonable temperature range
                    return temp

        # Fallback to simple extraction
        return self._extract_temperature(text)

    def _extract_with_patterns(self, text, patterns, *fallback_keywords):
        """Extract content using multiple patterns with fallback"""
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            if matches:
                # Return the first meaningful match
                for match in matches:
                    if isinstance(match, tuple):
                        match = ' '.join(m for m in match if m)
                    if match and len(match.strip()) > 10:  # Minimum length check
                        return match.strip()

        # Fallback to original method
        return self._extract_section(text, *fallback_keywords)

    def _extract_temperature_from_dict(self, data):
        """Extract temperature from parsed dictionary"""
        temp_keys = ['target_temperature', 'temperature', 'setpoint', 'recommended_temp']
        for key in temp_keys:
            if key in data and data[key]:
                if isinstance(data[key], (int, float)):
                    return int(data[key])
                elif isinstance(data[key], str):
                    return self._extract_temperature(data[key])
        return self._extract_temperature(str(data))

    def _validate_parsed_data(self, parsed_data, original_text):
        """Validate and clean parsed data"""
        # Ensure all required fields exist
        required_fields = ['ai_recommendation', 'target_temperature', 'energy_tips', 'comfort_advice',
                           'ventilation_advice']

        for field in required_fields:
            if field not in parsed_data or not parsed_data[field]:
                if field == 'target_temperature':
                    parsed_data[field] = self._extract_temperature(original_text)
                else:
                    keyword = field.replace('_', ' ')
                    parsed_data[field] = f"Analysis available in full recommendation below."

        # Ensure temperature is reasonable
        if not (16 <= parsed_data['target_temperature'] <= 28):
            parsed_data['target_temperature'] = 21  # Safe default

        return parsed_data

    def _extract_temperature(self, text):
        """Extract temperature from text"""
        temp_match = re.search(r'(\d+)[°\s]*[Cc]', text)
        return int(temp_match.group(1)) if temp_match else 21

    def _extract_section(self, text, *keywords):
        """Extract specific sections from AI response"""
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if any(keyword in line.lower() for keyword in keywords):
                # Return this line and the next few lines
                return ' '.join(lines[i:i + 3])
        return "No specific recommendations available."

    def _get_fallback_recommendations(self, room_data, weather_data):
        """Provide fallback recommendations when AI is unavailable"""
        # Handle None values with defaults
        room_temp = room_data.get('temperature', 20) or 20
        outside_temp = weather_data.get('temperature', 15) or 15

        # Simple logic-based fallback
        if room_temp > 24:
            recommendation = "Consider lowering temperature to 22°C"
        elif room_temp < 18:
            recommendation = "Consider increasing temperature to 21°C"
        else:
            recommendation = "Current temperature is optimal"

        return {
            'ai_recommendation': f"Fallback: {recommendation}",
            'target_temperature': 21,
            'energy_tips': "Maintain temperature between 20-22°C for optimal efficiency",
            'comfort_advice': "Current conditions are comfortable",
            'ventilation_advice': "Use natural ventilation when outside temperature is favorable",
            'is_fallback': True
        }