# Rental Booking Platform

A full-featured rental booking platform built with Django and Django REST Framework. The project allows users to browse listings, create bookings, manage reservations, leave reviews, and process payments through a secure REST API.

## Project Overview

This platform was developed as a portfolio project to demonstrate backend development skills using Python and Django.

The system includes:

* User authentication and authorization
* Property listings management
* Booking management
* Reviews and ratings
* Notifications
* Search functionality
* Payment processing
* Analytics and reporting
* REST API documentation

## Technology Stack

### Backend

* Python
* Django
* Django REST Framework
* JWT Authentication

### Database

* MySQL

### DevOps

* Docker
* Docker Compose

### Documentation

* Swagger / OpenAPI

## Features

### Authentication

* User registration
* User login
* JWT authentication
* Profile management

### Listings

* Create listings
* Update listings
* Delete listings
* Listing search and filtering
* Detailed listing information

### Booking System

* Create booking requests
* Manage reservations
* Booking status tracking
* Reservation history

### Reviews

* Leave reviews
* Property ratings
* User feedback system

### Payments

* Payment processing
* Transaction tracking

### Notifications

* User notifications
* Booking updates
* System alerts

### Analytics

* Booking statistics
* User activity insights

## Project Structure

```text
apps/
├── users/
├── listings/
├── bookings/
├── reviews/
├── payments/
├── notifications/
├── search/
└── analytics/
```

## Installation

### Clone Repository

```bash
git clone https://github.com/AnastasiiaProskurenko/rental-booking-platform.git
cd rental-booking-platform
```

### Create Virtual Environment

```bash
python -m venv venv
```

### Activate Environment

Windows:

```bash
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Database Migration

```bash
python manage.py migrate
```

### Create Superuser

```bash
python manage.py createsuperuser
```

### Run Development Server

```bash
python manage.py runserver
```

## Docker

Build and start the application:

```bash
docker-compose up --build
```

## API Documentation

Swagger documentation is available after starting the project:

```text
/api/docs/
```

OpenAPI schema:

```text
/api/schema/
```

## Testing

Run tests:

```bash
pytest
```

or

```bash
python manage.py test
```

## Future Improvements

* Recommendation system
* Advanced search filters
* AI-powered booking suggestions
* Real-time notifications
* Mobile application integration
* Multi-language support

## Skills Demonstrated

* Python development
* Django framework
* REST API design
* Authentication and authorization
* Database design
* Docker containerization
* Software architecture
* Backend development best practices

## Author

Anastasiia Proskurenko

GitHub:
https://github.com/AnastasiiaProskurenko
