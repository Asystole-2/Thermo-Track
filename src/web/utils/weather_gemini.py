import os
import requests
import logging
from datetime import datetime


class WeatherAIAnalyzer:
    def __init__(self):
        self.weather_api_key = os.environ.get('OPENWEATHER_API_KEY')
        self.base_url = "http://api.openweathermap.org/data/2.5/weather"
        self.logger = logging.getLogger(__name__)

        # Safe debug logging without print statements that can cause encoding issues
        self.logger.debug(f"Weather API Key exists: {bool(self.weather_api_key)}")

    def get_weather_data(self):
        """Get current weather data from OpenWeatherMap API"""
        try:
            # Use logger instead of print for safe debugging
            self.logger.debug("Attempting to fetch weather data")

            if not self.weather_api_key:
                self.logger.warning("OpenWeather API key not found")
                return self._get_default_weather_data()

            # Default to a major city if no specific location is provided
            params = {
                'q': 'Ireland,DUBLIN',  # Default location
                'appid': self.weather_api_key,
                'units': 'metric'
            }

            self.logger.debug(f"Making weather API request to: {self.base_url}")
            response = requests.get(self.base_url, params=params, timeout=10)

            self.logger.debug(f"Weather API response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                self.logger.debug("Successfully fetched weather data")
                return self._parse_weather_data(data)
            else:
                self.logger.warning(f"Weather API returned status {response.status_code}")
                return self._get_default_weather_data()

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Weather API request failed: {str(e)}")
            return self._get_default_weather_data()
        except Exception as e:
            self.logger.error(f"Unexpected error fetching weather data: {str(e)}")
            return self._get_default_weather_data()

    def _parse_weather_data(self, data):
        """Parse the weather API response"""
        try:
            weather_info = {
                'temperature': data['main']['temp'],
                'humidity': data['main']['humidity'],
                'pressure': data['main']['pressure'],
                'description': data['weather'][0]['description'],
                'wind_speed': data['wind']['speed'],
                'city': data['name'],
                'country': data['sys']['country'],
                'timestamp': datetime.now().isoformat()
            }
            self.logger.debug(f"Parsed weather data: {weather_info}")
            return weather_info
        except KeyError as e:
            self.logger.error(f"Missing key in weather data: {str(e)}")
            return self._get_default_weather_data()

    def _get_default_weather_data(self):
        """Return default weather data when API is unavailable"""
        self.logger.debug("Returning default weather data")
        return {
            'temperature': 20.0,
            'humidity': 50.0,
            'pressure': 1013.0,
            'description': 'clear sky',
            'wind_speed': 3.0,
            'city': 'Default City',
            'country': 'N/A',
            'timestamp': datetime.now().isoformat()
        }

    def generate_recommendations(self, room_data, weather_data, room_type="General"):
        """Generate HVAC recommendations based on room conditions and weather"""
        try:
            self.logger.debug(f"Generating recommendations for room type: {room_type}")

            room_temp = room_data.get('temperature', 21.0)
            room_humidity = room_data.get('humidity', 50.0)
            occupancy = room_data.get('occupancy', 0)
            outside_temp = weather_data.get('temperature', 20.0)
            outside_humidity = weather_data.get('humidity', 50.0)

            recommendations = {
                'target_temperature': 22.0,  # Default comfortable temperature
                'energy_saving_tip': '',
                'comfort_adjustment': '',
                'ventilation_suggestion': ''
            }

            # Temperature adjustments based on outside weather
            temp_difference = outside_temp - room_temp

            if temp_difference > 5:
                recommendations['target_temperature'] = room_temp + 1
                recommendations['energy_saving_tip'] = 'Consider natural cooling by opening windows'
            elif temp_difference < -5:
                recommendations['target_temperature'] = room_temp - 1
                recommendations['energy_saving_tip'] = 'Minimize heat loss by keeping windows closed'

            # Humidity control
            if room_humidity > 60:
                recommendations['comfort_adjustment'] = 'High humidity detected. Consider using dehumidifier.'
                recommendations['target_temperature'] -= 1  # Lower temp feels more comfortable in high humidity
            elif room_humidity < 30:
                recommendations['comfort_adjustment'] = 'Low humidity detected. Consider using humidifier.'
                recommendations['target_temperature'] += 1  # Higher temp feels more comfortable in low humidity

            # Occupancy-based adjustments
            if occupancy > 0:
                recommendations['target_temperature'] -= 1  # Cooler when occupied
                recommendations['ventilation_suggestion'] = 'Ensure adequate ventilation for occupant comfort'
            else:
                recommendations['energy_saving_tip'] = 'Room unoccupied. Consider setting back temperature by 2-3°C'

            # Room type specific adjustments
            if room_type.lower() in ['lab', 'server', 'equipment']:
                recommendations['target_temperature'] = 20.0  # Cooler for equipment rooms
                recommendations[
                    'comfort_adjustment'] = 'Equipment room: maintaining cooler temperature for device safety'
            elif room_type.lower() in ['office', 'workspace']:
                recommendations['target_temperature'] = 22.0  # Comfortable for work
            elif room_type.lower() in ['storage', 'warehouse']:
                recommendations['target_temperature'] = 18.0  # Cooler for storage

            self.logger.debug(f"Generated recommendations: {recommendations}")
            return recommendations

        except Exception as e:
            self.logger.error(f"Error generating recommendations: {str(e)}")
            return {
                'target_temperature': 22.0,
                'energy_saving_tip': 'Unable to generate specific recommendations',
                'comfort_adjustment': 'System error in recommendation engine',
                'ventilation_suggestion': ''
            }